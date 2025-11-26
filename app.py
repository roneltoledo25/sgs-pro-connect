import streamlit as st
import pandas as pd
import io
import time
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="SGS Pro Connect | Cloud",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STUNNING PROFESSIONAL CSS (Your Original Styles) ---
st.markdown("""
<style>
    /* Global Styles */
    .main { padding-top: 2rem; }
    h1, h2, h3 {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-weight: 600;
        letter-spacing: -0.5px;
    }
    /* Modern Card Styling for Metrics */
    [data-testid="stMetric"] {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.1);
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        transition: transform 0.2s ease;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.1);
    }
    /* Gradient Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #2b5876 0%, #4e4376 100%);
        color: white !important;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.6rem 1.2rem;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        opacity: 0.95;
    }
    /* Input Fields Polish */
    .stTextInput > div > div > input, .stSelectbox > div > div > div {
        border-radius: 8px;
    }
    /* Sidebar Profile Image */
    .profile-pic { 
        border-radius: 50%; 
        border: 3px solid var(--primary-color);
        padding: 3px;
    }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTS ---
SCHOOL_CODE = "SK2025"
SHEET_NAME = "SGS_Database" 
STUDENT_STATUSES = ["Active", "Transferred", "Dropped Out"]

# --- GOOGLE SHEETS CONNECTION & CACHING ---
def get_client():
    if 'gsheet_client' not in st.session_state:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # Load secrets from Streamlit Cloud Secrets
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        st.session_state.gsheet_client = gspread.authorize(creds)
    return st.session_state.gsheet_client

def get_worksheet(name):
    client = get_client()
    try:
        sh = client.open(SHEET_NAME)
        return sh.worksheet(name)
    except:
        # Create sheet if missing (Auto-Setup)
        sh = client.open(SHEET_NAME)
        ws = sh.add_worksheet(title=name, rows="100", cols="20")
        if name == "Users": ws.append_row(["username", "password", "role"])
        elif name == "Students": ws.append_row(["student_id", "student_name", "class_no", "grade_level", "room", "password", "status"])
        elif name == "Subjects": ws.append_row(["id", "teacher_username", "subject_name"])
        elif name == "Grades": ws.append_row(["student_id", "subject", "quarter", "school_year", "test1", "test2", "test3", "final_score", "total_score", "recorded_by"])
        return ws

# Helper to clear cache when we update data
def refresh_data():
    st.cache_data.clear()

@st.cache_data(ttl=60) # Cache data for 60 seconds to speed up the app
def fetch_all_data(sheet_name):
    ws = get_worksheet(sheet_name)
    return pd.DataFrame(ws.get_all_records())

# --- HELPER FUNCTIONS ---
def get_school_years():
    cy = datetime.datetime.now().year
    return [f"{cy}-{cy+1}", f"{cy+1}-{cy+2}", f"{cy+2}-{cy+3}"]

def fmt_score(val):
    if val is None or val == "": return "0"
    try:
        val = float(val)
        return f"{int(val)}" if val % 1 == 0 else f"{val:.1f}"
    except: return "0"

def get_grade_point(score):
    try: score = float(score)
    except: score = 0
    if score >= 80: return 4.0
    elif score >= 75: return 3.5
    elif score >= 70: return 3.0
    elif score >= 65: return 2.5
    elif score >= 60: return 2.0
    elif score >= 55: return 1.5
    elif score >= 50: return 1.0
    else: return 0.0

# --- BACKEND LOGIC (REPLACING SQLITE WITH GSPREAD) ---

def login_staff(username, password):
    df = fetch_all_data("Users")
    if df.empty: return None
    # Ensure columns are strings
    df = df.astype(str)
    user = df[(df['username'] == str(username)) & (df['password'] == str(password))]
    if not user.empty:
        return user.iloc[0].to_dict()
    return None

def login_student(student_id, password):
    df = fetch_all_data("Students")
    if df.empty: return None
    df = df.astype(str)
    stu = df[df['student_id'] == str(student_id)]
    
    if not stu.empty:
        data = stu.iloc[0]
        # Check Status
        if data['status'] != 'Active':
            return "NonActive" # Special flag
        
        # Check Password
        db_pass = data.get('password', '')
        if db_pass == '' or db_pass == 'nan':
            if str(password) == str(student_id): return data.to_dict()
        elif str(password) == str(db_pass):
            return data.to_dict()
    return None

def change_student_password(s_id, new_pass):
    ws = get_worksheet("Students")
    cell = ws.find(str(s_id))
    if cell:
        # Password is col 6 (F)
        ws.update_cell(cell.row, 6, new_pass)
        refresh_data()

def register_user(username, password, code):
    if code != SCHOOL_CODE: return False, "❌ Invalid School Code!"
    ws = get_worksheet("Users")
    try:
        if ws.find(username): return False, "⚠️ Username taken"
    except: pass
    
    ws.append_row([username, password, "Teacher"])
    refresh_data()
    return True, "✅ Success"

# --- DATA MANIPULATION FUNCTIONS ---

def get_admin_stats():
    t_count = len(fetch_all_data("Users"))
    s_count = len(fetch_all_data("Students"))
    sub_count = len(fetch_all_data("Subjects"))
    return t_count, s_count, sub_count

def get_all_teachers():
    df = fetch_all_data("Users")
    return df[df['role'] == 'Teacher']

def get_class_roster(level, room, only_active=False):
    df = fetch_all_data("Students")
    if df.empty: return df
    
    df = df.astype(str)
    # Filter
    mask = (df['grade_level'] == str(level)) & (df['room'] == str(room))
    if only_active:
        mask = mask & (df['status'] == 'Active')
        
    filtered = df[mask]
    # Sort by Class No (convert to int safely)
    if not filtered.empty:
        filtered['class_no_int'] = pd.to_numeric(filtered['class_no'], errors='coerce').fillna(0).astype(int)
        filtered = filtered.sort_values('class_no_int')
    return filtered

def get_next_class_no(level, room):
    df = get_class_roster(level, room, only_active=True)
    if df.empty: return 1
    try:
        return df['class_no'].astype(int).max() + 1
    except: return 1

def add_single_student(s_id, name, no, level, room):
    ws = get_worksheet("Students")
    try:
        if ws.find(str(s_id)): return False, f"⚠️ ID {s_id} exists!"
    except: pass
    
    # Defaults: Password empty, Status Active
    ws.append_row([str(s_id), name, no, level, room, "", "Active"])
    refresh_data()
    return True, f"✅ Added {name}"

def update_student_details(s_id, new_name, new_no):
    ws = get_worksheet("Students")
    try:
        cell = ws.find(str(s_id))
        if cell:
            ws.update_cell(cell.row, 2, new_name) # Name is col 2
            ws.update_cell(cell.row, 3, new_no)   # No is col 3
            refresh_data()
            return True, "✅ Updated"
    except Exception as e: return False, str(e)
    return False, "Not found"

def update_student_status(s_id, new_status):
    ws = get_worksheet("Students")
    try:
        cell = ws.find(str(s_id))
        if cell:
            ws.update_cell(cell.row, 7, new_status) # Status is col 7
            refresh_data()
            return True, f"✅ Status set to {new_status}"
    except Exception as e: return False, str(e)
    return False, "Not found"

def delete_single_student(s_id):
    ws = get_worksheet("Students")
    try:
        cell = ws.find(str(s_id))
        if cell:
            ws.delete_rows(cell.row)
            refresh_data()
            return True, "Deleted"
    except: pass
    return False, "Error"

def upload_roster(df, level, room):
    ws = get_worksheet("Students")
    added = 0
    # Prepare data to batch insert? No, row by row is safer for logic check
    # But batch is faster. For now, simple loop.
    existing_ids = [str(x) for x in ws.col_values(1)]
    
    for _, row in df.iterrows():
        s_id = str(row['ID']).strip().replace('.0', '')
        if s_id not in existing_ids:
            name = str(row['Name'])
            no = int(row['No'])
            ws.append_row([s_id, name, no, level, room, "", "Active"])
            added += 1
            existing_ids.append(s_id)
            
    refresh_data()
    return True, f"✅ Uploaded {added} students.", []

def get_teacher_subjects(teacher):
    df = fetch_all_data("Subjects")
    if df.empty: return []
    return df[df['teacher_username'] == str(teacher)][['id', 'subject_name']].values.tolist()

def add_subject(teacher, subject):
    ws = get_worksheet("Subjects")
    uid = f"{teacher}_{subject}".replace(" ", "")
    # Check duplicate
    df = fetch_all_data("Subjects")
    if not df.empty and uid in df['id'].values:
        return False, "Subject exists"
    
    ws.append_row([uid, teacher, subject])
    refresh_data()
    return True, "Added"

def delete_subject(sub_id):
    ws = get_worksheet("Subjects")
    try:
        cell = ws.find(str(sub_id))
        if cell:
            ws.delete_rows(cell.row)
            refresh_data()
    except: pass

def get_grade_record(student_id, subject, quarter, year):
    df = fetch_all_data("Grades")
    if df.empty: return None
    
    mask = (df['student_id'].astype(str) == str(student_id)) & \
           (df['subject'] == subject) & \
           (df['quarter'] == quarter) & \
           (df['school_year'] == year)
    
    data = df[mask]
    if not data.empty:
        r = data.iloc[0]
        # Return tuple like SQL used to
        return (r['test1'], r['test2'], r['test3'], r['final_score'], r['total_score'])
    return None

def save_grade(data):
    ws = get_worksheet("Grades")
    # Finding the row is complex. We iterate or use find? 
    # Composite keys are hard in Sheets. We will iterate rows in memory to find line number.
    records = ws.get_all_records()
    target_row = None
    
    # 1-based index for sheets, +1 for header = row 2 is first data
    for idx, row in enumerate(records):
        if (str(row['student_id']) == str(data['s_id']) and 
            row['subject'] == data['subj'] and 
            row['quarter'] == data['q'] and 
            row['school_year'] == data['year']):
            target_row = idx + 2
            break
            
    if target_row:
        # Update cols E(5) to J(10)
        # test1, test2, test3, final, total, recorded_by
        # Update range is faster
        cell_range = ws.range(f"E{target_row}:J{target_row}")
        vals = [data['t1'], data['t2'], data['t3'], data['final'], data['total'], data['teacher']]
        for i, cell in enumerate(cell_range):
            cell.value = vals[i]
        ws.update_cells(cell_range)
    else:
        # Append
        ws.append_row([
            data['s_id'], data['subj'], data['q'], data['year'],
            data['t1'], data['t2'], data['t3'], data['final'], data['total'], data['teacher']
        ])
    
    refresh_data()
    return True, "Saved Successfully"

def get_student_full_report(student_id):
    df = fetch_all_data("Grades")
    if df.empty: return df
    return df[df['student_id'].astype(str) == str(student_id)]

# --- UI COMPONENTS (YOUR ORIGINAL LAYOUT) ---

def login_screen():
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        st.markdown("## SGS Pro Connect")
        st.image("https://cdn-icons-png.flaticon.com/512/3413/3413535.png", width=300) # Placeholder Icon
    with c2:
        st.markdown("<div style='height: 50px;'></div>", unsafe_allow_html=True)
        st.title("🔐 Login Portal (Cloud)")
        
        login_role = st.radio("I am a:", ["Staff (Teacher/Admin)", "Student"], horizontal=True)

        if login_role == "Staff (Teacher/Admin)":
            tab1, tab2 = st.tabs(["Login", "Register"])
            with tab1:
                with st.form("t_login"):
                    u = st.text_input("Username")
                    p = st.text_input("Password", type="password")
                    if st.form_submit_button("Sign In", use_container_width=True):
                        user = login_staff(u, p)
                        if user:
                            st.session_state.user = user
                            st.session_state.role = user['role']
                            st.session_state.logged_in = True
                            st.rerun()
                        else: st.error("Invalid Credentials")
            with tab2:
                with st.form("reg_form"):
                    st.warning("Teacher Registration")
                    new_u = st.text_input("Username")
                    new_p = st.text_input("Password", type="password")
                    code = st.text_input("School Code", type="password")
                    if st.form_submit_button("Create Account", use_container_width=True):
                        ok, msg = register_user(new_u, new_p, code)
                        if ok: st.success(msg)
                        else: st.error(msg)
        
        else:
            st.info("ℹ️ First time? Use your Student ID as your password.")
            with st.form("s_login"):
                s_id = st.text_input("Student ID")
                s_pw = st.text_input("Password", type="password")
                if st.form_submit_button("Student Login", use_container_width=True):
                    stu = login_student(s_id, s_pw)
                    if stu == "NonActive": st.error("Account is not active.")
                    elif stu:
                        st.session_state.user = stu
                        st.session_state.role = "Student"
                        st.session_state.logged_in = True
                        st.rerun()
                    else: st.error("Invalid Credentials")

def sidebar_menu():
    with st.sidebar:
        role = st.session_state.get('role', 'Teacher')
        user_data = st.session_state.user
        
        if role == "Admin":
            st.markdown(f"### 🛡️ Admin")
            st.markdown("---")
            menu = st.radio("Menu", ["Dashboard", "👥 Manage Teachers", "🎓 Manage Students"])

        elif role == "Teacher":
            username = user_data['username']
            st.markdown(f"### 👨‍🏫 {username}")
            st.image("https://cdn-icons-png.flaticon.com/512/1995/1995539.png", width=120)
            st.markdown("---")
            menu = st.radio("Menu", ["Dashboard", "📂 Student Roster", "📝 Input Grades", "📊 Gradebook", "👤 Student Record"])
            
        else: # Student
            s_name = user_data['student_name']
            s_id = user_data['student_id']
            st.markdown(f"### 🎓 {s_name}")
            st.image("https://cdn-icons-png.flaticon.com/512/3237/3237472.png", width=120)
            st.caption(f"ID: {s_id}")
            st.markdown("---")
            menu = st.radio("Menu", ["📜 My Grades", "⚙️ Settings"])

        st.markdown("---")
        if st.button("🚪 Log Out", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
            
    return menu

# --- PAGE LOGIC ---

def page_dashboard():
    st.title("📊 Teacher Dashboard")
    # Quick Stats from Cloud
    roster_df = fetch_all_data("Students")
    active_count = len(roster_df[roster_df['status'] == 'Active']) if not roster_df.empty else 0
    
    col1, col2 = st.columns(2)
    col1.metric("Active Students", active_count)
    col2.metric("Active Year", get_school_years()[0])
    
    st.markdown("---")
    st.subheader("📚 Subject Management")
    
    with st.expander("➕ Add New Subject"):
        with st.form("add_sub_form"):
            new_s = st.text_input("Subject Name (e.g., Mathematics)")
            if st.form_submit_button("Add Subject"):
                ok, msg = add_subject(st.session_state.user['username'], new_s)
                if ok: st.rerun()
                else: st.error(msg)
    
    subjects = get_teacher_subjects(st.session_state.user['username'])
    if subjects:
        for sub_id, sub_name in subjects:
            with st.container():
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.markdown(f"#### 📘 {sub_name}")
                if c3.button("🗑️", key=f"del_{sub_id}"):
                    delete_subject(sub_id)
                    st.rerun()
                st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)
    else: st.info("No subjects added yet.")

def page_roster():
    st.title("📂 Student Roster")
    c1, c2 = st.columns(2)
    with c1: level = st.selectbox("Level", ["M1","M2","M3","M4","M5","M6"])
    with c2: room = st.selectbox("Room", [str(i) for i in range(1,16)])
    st.markdown("---")
    
    t1, t2, t3, t4, t5 = st.tabs(["📤 Bulk Upload", "➕ Manual Add", "✏️ Edit / Delete", "🔄 Update Status", "🗑️ Reset Class"])
    
    with t1:
        csv = pd.DataFrame({"ID":["10101","10102"], "Name":["Student A","Student B"], "No":[1,2]}).to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Template", csv, "template.csv", "text/csv")
        up_file = st.file_uploader("Excel/CSV", type=['xlsx','csv'])
        if up_file:
            if st.button("Upload"):
                try:
                    df = pd.read_csv(up_file) if up_file.name.endswith('.csv') else pd.read_excel(up_file)
                    ok, msg, errs = upload_roster(df, level, room)
                    if ok: st.success(msg)
                except Exception as e: st.error(str(e))
    
    with t2:
        next_no = get_next_class_no(level, room)
        with st.form("manual_add"):
            c_a, c_b, c_c = st.columns([1,3,1])
            m_id = c_a.text_input("ID")
            m_name = c_b.text_input("Name")
            m_no = c_c.number_input("No", value=next_no, disabled=True)
            if st.form_submit_button("✅ Add"):
                if m_id and m_name:
                    ok, msg = add_single_student(m_id, m_name, int(m_no), level, room)
                    if ok: st.success(msg); time.sleep(1); st.rerun()
                    else: st.error(msg)
    
    with t3:
        roster = get_class_roster(level, room, only_active=False)
        if not roster.empty:
            edit_target = st.selectbox("Select Student to Edit", roster['student_name'])
            target_row = roster[roster['student_name'] == edit_target].iloc[0]
            with st.form("edit_form"):
                e_id = st.text_input("ID", value=target_row['student_id'], disabled=True)
                e_name = st.text_input("Name", value=target_row['student_name'])
                e_no = st.number_input("Class No", value=int(target_row['class_no']))
                c_save, c_del = st.columns([1,1])
                if c_save.form_submit_button("💾 Save Changes"):
                    update_student_details(e_id, e_name, e_no); st.rerun()
                if c_del.form_submit_button("🗑️ Delete Permanently"):
                    delete_single_student(e_id); st.rerun()
    
    with t4:
        st.subheader("Update Student Status")
        roster_all = get_class_roster(level, room, only_active=False)
        if not roster_all.empty:
            roster_all['lbl'] = roster_all.apply(lambda x: f"{x['class_no']}. {x['student_name']} (Status: {x['status']})", axis=1)
            status_target_lbl = st.selectbox("Select Student", roster_all['lbl'], key='status_sel')
            
            if status_target_lbl:
                target_row = roster_all[roster_all['lbl'] == status_target_lbl].iloc[0]
                target_id = target_row['student_id']
                current_status = target_row['status']
                
                new_status = st.selectbox("Set New Status", STUDENT_STATUSES, index=STUDENT_STATUSES.index(current_status) if current_status in STUDENT_STATUSES else 0)
                
                if st.button("Update Status", use_container_width=True):
                    ok, msg = update_student_status(target_id, new_status)
                    if ok: st.success(msg); time.sleep(1); st.rerun()
                    else: st.error(msg)
                    
    with t5:
        st.error("⚠️ DANGER ZONE: This is slower on Cloud.")
        st.info("To delete a whole class, please do it directly in Google Sheets for speed.")

    st.subheader("Class Roster Overview")
    curr = get_class_roster(level, room, only_active=False)
    if not curr.empty:
        st.dataframe(curr[['class_no', 'student_id', 'student_name', 'status']], hide_index=True, use_container_width=True)

def page_input_grades():
    st.title("📝 Class Record Input")
    subs_raw = get_teacher_subjects(st.session_state.user['username'])
    subjects = [s[1] for s in subs_raw]
    if not subjects: st.warning("Add subjects first."); return

    with st.expander("⚙️ Settings", expanded=True):
        c1,c2,c3,c4,c5 = st.columns(5)
        yr = c1.selectbox("Year", get_school_years())
        subj = c2.selectbox("Subject", subjects)
        q = c3.selectbox("Quarter", ["Q1","Q2","Q3","Q4"])
        lvl = c4.selectbox("Level", ["M1","M2","M3","M4","M5","M6"])
        rm = c5.selectbox("Room", [str(i) for i in range(1,16)])

    roster = get_class_roster(lvl, rm, only_active=True)
    if roster.empty: st.warning("No Active students."); return

    # Simplified progress bar logic for cloud speed
    roster['lbl'] = roster.apply(lambda x: f"{x['class_no']}. {x['student_name']}", axis=1)
    sel_lbl = st.selectbox("Choose Student:", roster['lbl'])
    sel_row = roster[roster['lbl'] == sel_lbl].iloc[0]
    s_id, s_name = sel_row['student_id'], sel_row['student_name']

    st.markdown("---")
    left, right = st.columns([1, 2.5])
    with left:
        st.markdown(f"**{s_name}**")
        st.image("https://cdn-icons-png.flaticon.com/512/3237/3237472.png", width=150)

    with right:
        ex = get_grade_record(s_id, subj, q, yr)
        # Defaults
        t1, t2, t3, final_score = 0.0, 0.0, 0.0, 0.0
        if ex:
             t1, t2, t3, final_score, total_score = [float(x) if x != '' else 0.0 for x in ex]
             st.info(f"Existing Total: {total_score:.1f}")

        st.subheader("📊 Score Calculator")
        with st.form("cal_form"):
            c1, c2, c3, c4 = st.columns([2.5, 1.2, 1.2, 1.1])
            c1.markdown("**Task**"); c2.markdown("**Score**"); c3.markdown("**Max**"); c4.markdown("**Weight**")
            
            # Recreating your EXACT calculator logic
            # T1
            c1, c2, c3, c4 = st.columns([2.5, 1.2, 1.2, 1.1])
            c1.text_input("L1", "Test 1", key="l1", label_visibility="collapsed")
            r1 = c2.number_input("R1", 0, 999, value=int(t1*10), key="r1", label_visibility="collapsed") # Approx reverse
            m1 = c3.number_input("M1", 1, 999, value=100, key="m1", label_visibility="collapsed")
            f1 = min((r1/m1)*10 if m1>0 else 0, 10.0)
            c4.metric("10", fmt_score(f1), label_visibility="collapsed")
            
            # T2
            c1, c2, c3, c4 = st.columns([2.5, 1.2, 1.2, 1.1])
            c1.text_input("L2", "Test 2", key="l2", label_visibility="collapsed")
            r2 = c2.number_input("R2", 0, 999, value=int(t2*10), key="r2", label_visibility="collapsed")
            m2 = c3.number_input("M2", 1, 999, value=100, key="m2", label_visibility="collapsed")
            f2 = min((r2/m2)*10 if m2>0 else 0, 10.0)
            c4.metric("10", fmt_score(f2), label_visibility="collapsed")
            
            # T3
            c1, c2, c3, c4 = st.columns([2.5, 1.2, 1.2, 1.1])
            c1.text_input("L3", "Test 3", key="l3", label_visibility="collapsed")
            r3 = c2.number_input("R3", 0, 999, value=int(t3*10), key="r3", label_visibility="collapsed")
            m3 = c3.number_input("M3", 1, 999, value=100, key="m3", label_visibility="collapsed")
            f3 = min((r3/m3)*10 if m3>0 else 0, 10.0)
            c4.metric("10", fmt_score(f3), label_visibility="collapsed")
            
            # Final
            c1, c2, c3, c4 = st.columns([2.5, 1.2, 1.2, 1.1])
            c1.text_input("L4", "Final", key="l4", label_visibility="collapsed")
            rf = c2.number_input("RF", 0, 999, value=int(final_score*2.5), key="rf", label_visibility="collapsed")
            mf = c3.number_input("MF", 1, 999, value=50, key="mf", label_visibility="collapsed")
            ff = min((rf/mf)*20 if mf>0 else 0, 20.0)
            c4.metric("20", fmt_score(ff), label_visibility="collapsed")
            
            total = f1+f2+f3+ff
            st.markdown("---")
            st.markdown(f"### 🏆 Total: {total:.1f} / 50")
            
            if st.form_submit_button("💾 Save", use_container_width=True):
                save_grade({
                    "s_id":s_id, "subj":subj, "q":q, "year":yr,
                    "t1":f1, "t2":f2, "t3":f3, "final":ff, "total":total,
                    "teacher":st.session_state.user['username']
                })
                st.success("Saved!"); time.sleep(1); st.rerun()

def page_gradebook():
    st.title("📊 Gradebook")
    subs_raw = get_teacher_subjects(st.session_state.user['username'])
    subjects = [s[1] for s in subs_raw]
    if not subjects: st.warning("No subjects"); return
    
    c1,c2,c3,c4 = st.columns(4)
    s = c1.selectbox("Subject", subjects)
    l = c2.selectbox("Level", ["M1","M2","M3","M4","M5","M6"])
    r = c3.selectbox("Room", [str(i) for i in range(1,16)])
    q = c4.selectbox("Quarter", ["Q1","Q2","Q3","Q4"])
    
    # Complex join simulation in Pandas
    students = get_class_roster(l, r, only_active=True)
    grades = fetch_all_data("Grades")
    
    if not students.empty and not grades.empty:
        # Filter grades
        grades = grades.astype(str)
        g_filtered = grades[
            (grades['subject'] == s) & 
            (grades['quarter'] == q)
        ]
        
        # Merge
        students['student_id'] = students['student_id'].astype(str)
        merged = pd.merge(students, g_filtered, on='student_id', how='left')
        
        # Display
        display = merged[['class_no', 'student_id', 'student_name', 'test1', 'test2', 'test3', 'final_score', 'total_score']]
        st.dataframe(display, hide_index=True, use_container_width=True)
        
        csv = display.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download Excel/CSV", csv, f"gradebook_{l}_{r}.csv", "text/csv")
    else:
        st.warning("No data found.")

def page_student_record_teacher_view():
    st.title("👤 Student Record Search")
    s_search = st.text_input("Enter Student ID")
    if s_search:
        df = fetch_all_data("Students")
        df = df.astype(str)
        res = df[df['student_id'] == s_search]
        if not res.empty:
            stu = res.iloc[0]
            st.markdown(f"### {stu['student_name']} (Status: {stu['status']})")
            
            # Show grades
            g = fetch_all_data("Grades")
            g = g.astype(str)
            # Filter by this student AND this teacher's subjects
            my_subs = [x[1] for x in get_teacher_subjects(st.session_state.user['username'])]
            
            stu_grades = g[
                (g['student_id'] == s_search) & 
                (g['subject'].isin(my_subs))
            ]
            
            if not stu_grades.empty:
                st.dataframe(stu_grades[['school_year','quarter','subject','total_score']], hide_index=True)
            else: st.warning("No grades with you.")
        else: st.error("Not found.")

def page_student_portal_grades():
    st.title("📜 My Academic Record")
    sid = st.session_state.user['student_id']
    df = get_student_full_report(sid)
    if not df.empty:
        # Pivot logic for nicer view
        try:
            df['total_score'] = pd.to_numeric(df['total_score'], errors='coerce')
            pivot = df.pivot_table(index=['school_year', 'subject'], columns='quarter', values='total_score', aggfunc='first').reset_index()
            st.dataframe(pivot, hide_index=True, use_container_width=True)
        except:
            st.dataframe(df)
    else:
        st.warning("No grades yet.")

def page_student_settings():
    st.title("⚙️ Settings")
    with st.form("pwd"):
        p1 = st.text_input("New Password", type="password")
        p2 = st.text_input("Confirm", type="password")
        if st.form_submit_button("Update"):
            if p1 == p2 and p1:
                change_student_password(st.session_state.user['student_id'], p1)
                st.success("Updated! Log in again.")

# --- ADMIN PAGES ---
def page_admin_dashboard():
    st.title("🛡️ Admin Dashboard")
    t, s, sub = get_admin_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Teachers", t)
    c2.metric("Students", s)
    c3.metric("Subjects", sub)

def page_admin_manage_teachers():
    st.title("👥 Manage Teachers")
    df = get_all_teachers()
    st.dataframe(df[['username', 'role']], hide_index=True)

def page_admin_manage_students():
    st.title("🎓 Manage Students")
    st.info("Use the Roster page or Google Sheets directly for bulk edits.")

# --- MAIN ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login_screen()
else:
    sel = sidebar_menu()
    
    if st.session_state.role == "Admin":
        if sel == "Dashboard": page_admin_dashboard()
        elif sel == "👥 Manage Teachers": page_admin_manage_teachers()
        elif sel == "🎓 Manage Students": page_admin_manage_students()
    
    elif st.session_state.role == "Teacher":
        if sel == "Dashboard": page_dashboard()
        elif sel == "📂 Student Roster": page_roster()
        elif sel == "📝 Input Grades": page_input_grades()
        elif sel == "📊 Gradebook": page_gradebook()
        elif sel == "👤 Student Record": page_student_record_teacher_view()
        
    elif st.session_state.role == "Student":
        if sel == "📜 My Grades": page_student_portal_grades()
        elif sel == "⚙️ Settings": page_student_settings()