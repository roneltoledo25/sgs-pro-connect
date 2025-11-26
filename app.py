import streamlit as st
import pandas as pd
import io
import time
import datetime
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
import base64

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="SGS Pro Connect | Admin",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STUNNING PROFESSIONAL CSS ---
st.markdown("""
<style>
    .main { padding-top: 2rem; }
    h1, h2, h3 { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-weight: 600; letter-spacing: -0.5px; }
    [data-testid="stMetric"] { background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.1); padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05); transition: transform 0.2s ease; }
    [data-testid="stMetric"]:hover { transform: translateY(-2px); box-shadow: 0 6px 12px rgba(0, 0, 0, 0.1); }
    .stButton > button { background: linear-gradient(135deg, #2b5876 0%, #4e4376 100%); color: white !important; border: none; border-radius: 8px; font-weight: 600; letter-spacing: 0.5px; padding: 0.6rem 1.2rem; transition: all 0.3s ease; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.2); opacity: 0.95; }
    .stButton > button:active { transform: translateY(0); }
    .stTextInput > div > div > input, .stSelectbox > div > div > div { border-radius: 8px; }
    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; border: 1px solid rgba(128, 128, 128, 0.1); }
    .profile-pic { border-radius: 50%; border: 3px solid var(--primary-color); padding: 3px; }
    .streamlit-expanderHeader { font-weight: 600; background-color: var(--secondary-background-color); border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTS ---
SHEET_NAME = "SGS_Database" 
SCHOOL_CODE = "SK2025"
STUDENT_STATUSES = ["Active", "Transferred", "Dropped Out"]

# --- GOOGLE SHEETS CONNECTION (RAW JSON VERSION) ---
@st.cache_resource
def get_db_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Read the raw JSON string from secrets and parse it
    try:
        json_str = st.secrets["gcp"]["service_account_json"]
        creds_dict = json.loads(json_str)
        
        # Connect using the parsed dictionary
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"❌ Database Connection Error: {e}")
        st.stop()

# Helper to check/create headers if sheet is empty
def init_db():
    try:
        sh = get_db_connection()
        
        # 1. Users Tab
        w_users = sh.worksheet("Users")
        if not w_users.get_all_values():
            w_users.append_row(["username", "password", "role", "profile_pic"])
            w_users.append_row(["admin", "admin123", "Admin", ""])

        # 2. Subjects Tab
        w_subs = sh.worksheet("Subjects")
        if not w_subs.get_all_values():
            w_subs.append_row(["id", "teacher_username", "subject_name"])

        # 3. Students Tab
        w_studs = sh.worksheet("Students")
        if not w_studs.get_all_values():
            w_studs.append_row(["student_id", "student_name", "class_no", "grade_level", "room", "photo", "password", "status"])

        # 4. Grades Tab
        w_grades = sh.worksheet("Grades")
        if not w_grades.get_all_values():
            w_grades.append_row(["id", "student_id", "subject", "quarter", "school_year", "test1", "test2", "test3", "final_score", "total_score", "recorded_by", "timestamp"])
            
    except Exception as e:
        st.error(f"Database Initialization Error: {e}")

# --- HELPER FUNCTIONS ---
def get_school_years():
    current_year = datetime.datetime.now().year
    return [f"{current_year}-{current_year+1}", f"{current_year+1}-{current_year+2}", f"{current_year+2}-{current_year+3}"]

def fmt_score(val):
    if val % 1 == 0: return f"{int(val)}"
    return f"{val:.1f}"

def get_grade_point(score):
    if score >= 80: return 4.0
    elif score >= 75: return 3.5
    elif score >= 70: return 3.0
    elif score >= 65: return 2.5
    elif score >= 60: return 2.0
    elif score >= 55: return 1.5
    elif score >= 50: return 1.0
    else: return 0.0

def image_to_base64(img_bytes):
    if not img_bytes: return ""
    return base64.b64encode(img_bytes).decode('utf-8')

def base64_to_image(b64_str):
    if not b64_str: return None
    try:
        return base64.b64decode(b64_str)
    except: return None

# --- BACKEND FUNCTIONS (GOOGLE SHEETS) ---

def login_staff(username, password):
    sh = get_db_connection()
    ws = sh.worksheet("Users")
    records = ws.get_all_records()
    for row in records:
        if str(row['username']) == str(username) and str(row['password']) == str(password):
            return (row['username'], row['password'], row['role'], base64_to_image(row['profile_pic']))
    return None

def login_student(student_id, password):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    records = ws.get_all_records()
    s_id_in = str(student_id).strip()
    
    for row in records:
        if str(row['student_id']).strip() == s_id_in:
            if row['status'] != 'Active': return None
            
            db_pass = str(row['password'])
            is_valid = False
            if not db_pass and str(password) == s_id_in: is_valid = True
            elif str(password) == db_pass: is_valid = True
            
            if is_valid:
                return (row['student_id'], row['student_name'], row['password'], base64_to_image(row['photo']), row['status'])
    return None

def change_student_password(s_id, new_pass):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell: ws.update_cell(cell.row, 7, new_pass)

def register_user(username, password, code):
    if code != SCHOOL_CODE: return False, "❌ Invalid School Code!"
    sh = get_db_connection()
    ws = sh.worksheet("Users")
    if ws.find(username): return False, "⚠️ Username taken"
    ws.append_row([username, password, 'Teacher', ""])
    return True, "✅ Success"

# --- ADMIN FUNCTIONS ---
def get_admin_stats():
    sh = get_db_connection()
    t_count = len(sh.worksheet("Users").get_all_values()) - 1 
    s_count = len(sh.worksheet("Students").get_all_values()) - 1
    sub_count = len(sh.worksheet("Subjects").get_all_values()) - 1
    return t_count, s_count, sub_count

def get_all_teachers_with_counts():
    sh = get_db_connection()
    users = sh.worksheet("Users").get_all_records()
    subs = sh.worksheet("Subjects").get_all_records()
    data = []
    for u in users:
        if u['role'] == 'Teacher':
            count = sum(1 for s in subs if s['teacher_username'] == u['username'])
            data.append({'username': u['username'], 'password': u['password'], 'subject_count': count})
    return pd.DataFrame(data)

def delete_teacher(username):
    sh = get_db_connection()
    ws_u = sh.worksheet("Users")
    cell = ws_u.find(username)
    if cell: ws_u.delete_rows(cell.row)
    
    ws_s = sh.worksheet("Subjects")
    all_s = ws_s.get_all_records()
    new_s = [row for row in all_s if row['teacher_username'] != username]
    ws_s.clear()
    ws_s.append_row(["id", "teacher_username", "subject_name"])
    for r in new_s: ws_s.append_row([r['id'], r['teacher_username'], r['subject_name']])

def admin_reset_teacher_password(username, new_pass):
    sh = get_db_connection()
    ws = sh.worksheet("Users")
    cell = ws.find(username)
    if cell: ws.update_cell(cell.row, 2, new_pass)

def get_all_students_admin():
    sh = get_db_connection()
    data = sh.worksheet("Students").get_all_records()
    for d in data: d['student_id'] = str(d['student_id'])
    return pd.DataFrame(data)

def delete_student_admin(s_id):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell: ws.delete_rows(cell.row)
    
    ws_g = sh.worksheet("Grades")
    all_g = ws_g.get_all_records()
    new_g = [r for r in all_g if str(r['student_id']) != str(s_id)]
    ws_g.clear()
    ws_g.append_row(["id", "student_id", "subject", "quarter", "school_year", "test1", "test2", "test3", "final_score", "total_score", "recorded_by", "timestamp"])
    for r in new_g: ws_g.append_row(list(r.values()))

def admin_reset_student_password(s_id, new_pass):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell: ws.update_cell(cell.row, 7, new_pass)

# --- GENERAL FUNCTIONS ---
def update_teacher_pic(username, image_bytes):
    sh = get_db_connection()
    ws = sh.worksheet("Users")
    cell = ws.find(username)
    if cell: ws.update_cell(cell.row, 4, image_to_base64(image_bytes))

def update_student_pic(student_id, image_bytes):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(student_id))
    if cell: ws.update_cell(cell.row, 6, image_to_base64(image_bytes))

def get_teacher_data(username):
    user = login_staff(username, "") 
    if user: return user[3] 
    return None

def get_student_photo(student_id):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    records = ws.get_all_records()
    for r in records:
        if str(r['student_id']) == str(student_id):
            return base64_to_image(r['photo'])
    return None

def get_student_details(student_id):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    records = ws.get_all_records()
    for r in records:
        if str(r['student_id']) == str(student_id):
            return (r['student_name'], r['grade_level'], r['room'], base64_to_image(r['photo']), r['status'])
    return None

def get_next_class_no(level, room):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    records = ws.get_all_records()
    max_no = 0
    for r in records:
        if r['grade_level'] == level and str(r['room']) == str(room) and r['status'] == 'Active':
            if int(r['class_no']) > max_no: max_no = int(r['class_no'])
    return max_no + 1

def add_single_student(s_id, name, no, level, room):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    try:
        if ws.find(str(s_id)): return False, f"⚠️ Student ID {s_id} already exists!"
    except: pass
    ws.append_row([str(s_id), name, no, level, room, "", "", "Active"])
    return True, f"✅ Added {name}"

def update_student_details(s_id, new_name, new_no):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell:
        ws.update_cell(cell.row, 2, new_name)
        ws.update_cell(cell.row, 3, new_no)
        return True, "Updated"
    return False, "Not found"

def update_student_status(s_id, new_status):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell:
        ws.update_cell(cell.row, 8, new_status)
        return True, f"Status updated to {new_status}"
    return False, "Error"

def delete_single_student(s_id):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell:
        ws.delete_rows(cell.row)
        return True, "Deleted"
    return False, "Error"

def delete_entire_roster(level, room):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    all_data = ws.get_all_records()
    keep_data = [r for r in all_data if not (r['grade_level'] == level and str(r['room']) == str(room))]
    ws.clear()
    ws.append_row(["student_id", "student_name", "class_no", "grade_level", "room", "photo", "password", "status"])
    for r in keep_data: ws.append_row(list(r.values()))
    return True, "Cleared"

def upload_roster(df, level, room):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    existing_ids = [str(r['student_id']) for r in ws.get_all_records()]
    added = 0
    errors = []
    rows_to_add = []
    for index, row in df.iterrows():
        s_id = str(row['ID']).strip()
        if s_id.endswith('.0'): s_id = s_id[:-2]
        if s_id in existing_ids:
            errors.append(f"Skipped {s_id} (Duplicate)")
            continue
        rows_to_add.append([s_id, str(row['Name']), int(row['No']), level, room, "", "", "Active"])
        existing_ids.append(s_id)
        added += 1
    if rows_to_add: ws.append_rows(rows_to_add)
    return True, f"✅ Uploaded {added}", errors

def get_class_roster(level, room, only_active=False):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    records = ws.get_all_records()
    filtered = []
    for r in records:
        if r['grade_level'] == level and str(r['room']) == str(room):
            if only_active and r['status'] != 'Active': continue
            filtered.append(r)
    df = pd.DataFrame(filtered)
    if not df.empty:
        df['student_id'] = df['student_id'].astype(str)
        df = df.sort_values('class_no')
    return df

def get_teacher_subjects_full(teacher):
    sh = get_db_connection()
    ws = sh.worksheet("Subjects")
    records = ws.get_all_records()
    res = []
    for r in records:
        if r['teacher_username'] == teacher:
            res.append((r['id'], r['subject_name']))
    return res

def add_subject(teacher, subject):
    sh = get_db_connection()
    ws = sh.worksheet("Subjects")
    records = ws.get_all_records()
    for r in records:
        if r['teacher_username'] == teacher and r['subject_name'] == subject:
            return False, "⚠️ You already have this subject."
    new_id = int(time.time())
    ws.append_row([new_id, teacher, subject])
    return True, "Added"

def delete_subject(sub_id):
    sh = get_db_connection()
    ws = sh.worksheet("Subjects")
    records = ws.get_all_records()
    for i, r in enumerate(records):
        if str(r['id']) == str(sub_id):
            ws.delete_rows(i + 2)
            return

def update_subject(sub_id, new_name):
    sh = get_db_connection()
    ws = sh.worksheet("Subjects")
    records = ws.get_all_records()
    for i, r in enumerate(records):
        if str(r['id']) == str(sub_id):
            ws.update_cell(i + 2, 3, new_name)
            return True
    return False

def get_grade_record(student_id, subject, quarter, year):
    sh = get_db_connection()
    ws = sh.worksheet("Grades")
    records = ws.get_all_records()
    for r in records:
        if (str(r['student_id']) == str(student_id) and 
            r['subject'] == subject and 
            r['quarter'] == quarter and 
            r['school_year'] == year):
            return (r['test1'], r['test2'], r['test3'], r['final_score'], r['total_score'])
    return None

def save_grade(data):
    sh = get_db_connection()
    ws = sh.worksheet("Grades")
    records = ws.get_all_records()
    row_idx = None
    for i, r in enumerate(records):
        if (str(r['student_id']) == str(data['s_id']) and 
            r['subject'] == data['subj'] and 
            r['quarter'] == data['q'] and 
            r['school_year'] == data['year']):
            row_idx = i + 2
            break
            
    if row_idx:
        ws.update_cell(row_idx, 6, data['t1'])
        ws.update_cell(row_idx, 7, data['t2'])
        ws.update_cell(row_idx, 8, data['t3'])
        ws.update_cell(row_idx, 9, data['final'])
        ws.update_cell(row_idx, 10, data['total'])
        ws.update_cell(row_idx, 11, data['teacher'])
        ws.update_cell(row_idx, 12, str(datetime.datetime.now()))
    else:
        ws.append_row([int(time.time()), str(data['s_id']), data['subj'], data['q'], data['year'],
                       data['t1'], data['t2'], data['t3'], data['final'], data['total'],
                       data['teacher'], str(datetime.datetime.now())])
    return True, "Saved"

def get_student_full_report(student_id):
    sh = get_db_connection()
    ws = sh.worksheet("Grades")
    records = ws.get_all_records()
    data = []
    for r in records:
        if str(r['student_id']) == str(student_id):
            data.append(r)
    return pd.DataFrame(data)

def get_student_grades_for_teacher_view(student_id, teacher_username):
    sh = get_db_connection()
    ws = sh.worksheet("Grades")
    records = ws.get_all_records()
    data = []
    for r in records:
        if str(r['student_id']) == str(student_id) and r['recorded_by'] == teacher_username:
            data.append(r)
    return pd.DataFrame(data)

# --- UI COMPONENTS ---
def login_screen():
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        st.markdown("## SGS Pro Connect")
        st.image("logo/images.jpeg", width=300)
    with c2:
        st.markdown("<div style='height: 50px;'></div>", unsafe_allow_html=True)
        st.title("🔐 Login Portal")
        login_role = st.radio("I am a:", ["Staff (Teacher/Admin)", "Student"], horizontal=True)

        if login_role == "Staff (Teacher/Admin)":
            tab1, tab2 = st.tabs(["Login", "Register"])
            with tab1:
                with st.form("t_login"):
                    u = st.text_input("Username")
                    p = st.text_input("Password", type="password")
                    if st.form_submit_button("Sign In", width="stretch"):
                        user = login_staff(u, p)
                        if user:
                            st.session_state.user = user
                            st.session_state.role = user[2]
                            st.session_state.logged_in = True
                            st.rerun()
                        else: st.error("Invalid Credentials")
            with tab2:
                with st.form("reg_form"):
                    st.warning("Teacher Registration")
                    new_u = st.text_input("Username")
                    new_p = st.text_input("Password", type="password")
                    code = st.text_input("School Code", type="password")
                    if st.form_submit_button("Create Account", width="stretch"):
                        ok, msg = register_user(new_u, new_p, code)
                        if ok: st.success(msg)
                        else: st.error(msg)
        else:
            st.info("ℹ️ First time? Use your Student ID as your password.")
            with st.form("s_login"):
                s_id = st.text_input("Student ID")
                s_pw = st.text_input("Password", type="password")
                if st.form_submit_button("Student Login", width="stretch"):
                    stu = login_student(s_id, s_pw)
                    if stu:
                        st.session_state.user = stu
                        st.session_state.role = "Student"
                        st.session_state.logged_in = True
                        st.rerun()
                    else: st.error("Invalid ID or Password, or student is not marked as 'Active'.")

def sidebar_menu():
    with st.sidebar:
        role = st.session_state.get('role', 'Teacher')
        user_data = st.session_state.user
        if role == "Admin":
            st.markdown(f"### 🛡️ Admin")
            st.markdown("---")
            menu = st.radio("Menu", ["Dashboard", "👥 Manage Teachers", "🎓 Manage Students"])
        elif role == "Teacher":
            username = user_data[0]
            st.markdown(f"### 👨‍🏫 {username}")
            pic = user_data[3]
            if pic: st.image(Image.open(io.BytesIO(pic)), width=120)
            else: st.image("https://cdn-icons-png.flaticon.com/512/1995/1995539.png", width=120)
            with st.expander("📷 Photo"):
                up = st.file_uploader("Up", type=['jpg','png'], label_visibility="collapsed")
                if up: 
                    update_teacher_pic(username, up.getvalue())
                    st.success("Updated! Relogin to see change.")
            st.markdown("---")
            menu = st.radio("Menu", ["Dashboard", "📂 Student Roster", "📝 Input Grades", "📊 Gradebook", "👤 Student Record"])
        else: 
            s_name = user_data[1]
            s_id = user_data[0]
            s_pic = user_data[3]
            st.markdown(f"### 🎓 {s_name}")
            if s_pic: st.image(Image.open(io.BytesIO(s_pic)), width=120)
            else: st.image("https://cdn-icons-png.flaticon.com/512/3237/3237472.png", width=120)
            st.caption(f"ID: {s_id}")
            st.markdown("---")
            menu = st.radio("Menu", ["📜 My Grades", "⚙️ Settings"])
        st.markdown("---")
        if st.button("🚪 Log Out", width="stretch"):
            st.session_state.logged_in = False
            st.rerun()
    return menu

def page_admin_dashboard():
    st.title("🛡️ Admin Dashboard")
    t, s, sub = get_admin_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Teachers", t)
    c2.metric("Total Students", s)
    c3.metric("Total Subjects", sub)
    st.markdown("---")
    st.info("Select 'Manage Teachers' or 'Manage Students' from the sidebar.")

def page_admin_manage_teachers():
    st.title("👥 Manage Teachers")
    df = get_all_teachers_with_counts()
    if not df.empty:
        for idx, row in df.iterrows():
            with st.expander(f"👨‍🏫 {row['username']} (Subjects: {row['subject_count']})"):
                c1, c2 = st.columns([2, 1])
                with c1:
                    new_p = st.text_input("New Password", key=f"tp_{row['username']}")
                    if st.button("Update Password", key=f"tup_{row['username']}"):
                        if new_p:
                            admin_reset_teacher_password(row['username'], new_p)
                            st.success("Password Updated")
                with c2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("🗑️ Delete Account", key=f"tdel_{row['username']}"):
                        delete_teacher(row['username'])
                        st.warning("Deleted!"); time.sleep(1); st.rerun()
    else: st.warning("No teachers found.")

def page_admin_manage_students():
    st.title("🎓 Manage Students")
    df = get_all_students_admin()
    search = st.text_input("🔍 Search Student ID or Name")
    if search and not df.empty:
        df = df[df['student_name'].str.contains(search, case=False) | df['student_id'].astype(str).str.contains(search)]
    st.dataframe(df, width="stretch", hide_index=True)
    st.markdown("### ✏️ Edit Student Account")
    c1, c2, c3 = st.columns([1,2,1])
    target_id = c1.text_input("Enter ID to Edit")
    if target_id:
        with c2.form("admin_stu_edit"):
            new_pass = st.text_input("Set New Password")
            if st.form_submit_button("Reset Password"):
                admin_reset_student_password(target_id, new_pass)
                st.success(f"Password for {target_id} reset.")
        if c3.button("🗑️ Delete Student", key="del_stu_adm"):
            delete_student_admin(target_id)
            st.warning(f"Student {target_id} deleted."); time.sleep(1); st.rerun()

def page_dashboard():
    st.title("📊 Teacher Dashboard")
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    recs = ws.get_all_records()
    total_students = sum(1 for r in recs if r['status'] == 'Active')
    c1, c2 = st.columns(2)
    c1.metric("Active Students", total_students)
    c2.metric("Active Year", get_school_years()[0])
    st.markdown("---")
    st.subheader("📚 Subject Management")
    with st.expander("➕ Add New Subject"):
        with st.form("add_sub_form"):
            new_s = st.text_input("Subject Name")
            st.caption("Subject names must be unique.")
            if st.form_submit_button("Add Subject"):
                ok, msg = add_subject(st.session_state.user[0], new_s)
                if ok: st.rerun()
                else: st.error(msg)
    subjects = get_teacher_subjects_full(st.session_state.user[0])
    if subjects:
        for sub_id, sub_name in subjects:
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1.5, 1, 1])
                c1.markdown(f"#### 📘 {sub_name}")
                with c3.popover("✏️ Edit"):
                    edit_name = st.text_input("Rename", value=sub_name, key=f"edit_{sub_id}")
                    if st.button("Save", key=f"save_{sub_id}"):
                        if update_subject(sub_id, edit_name): st.rerun()
                        else: st.error("Error")
                if c4.button("🗑️", key=f"del_{sub_id}"):
                    delete_subject(sub_id); st.rerun()
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
        csv = pd.DataFrame({"ID":["10101"], "Name":["Student A"], "No":[1]}).to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Template", csv, "template.csv", "text/csv")
        up_file = st.file_uploader("Excel/CSV", type=['xlsx','csv'])
        if up_file:
            if st.button("Upload"):
                try:
                    df = pd.read_csv(up_file) if up_file.name.endswith('.csv') else pd.read_excel(up_file)
                    ok, msg, errs = upload_roster(df, level, room)
                    if ok: st.success(msg)
                    if errs: st.error(f"{len(errs)} Errors")
                except Exception as e: st.error(str(e))
    with t2:
        next_no = get_next_class_no(level, room)
        with st.form("manual_add"):
            c1, c2, c3 = st.columns([1,3,1])
            m_id = c1.text_input("ID")
            m_name = c2.text_input("Name")
            m_no = c3.number_input("No", value=next_no, disabled=True)
            if st.form_submit_button("✅ Add"):
                if m_id and m_name:
                    ok, msg = add_single_student(m_id, m_name, int(m_no), level, room)
                    if ok: st.success(msg); time.sleep(1); st.rerun()
                    else: st.error(msg)
    with t3:
        roster = get_class_roster(level, room, only_active=False) 
        if not roster.empty:
            edit_target = st.selectbox("Select Student", roster['student_name'])
            target_row = roster[roster['student_name'] == edit_target].iloc[0]
            with st.form("edit_form"):
                e_id = st.text_input("ID", value=target_row['student_id'], disabled=True)
                e_name = st.text_input("Name", value=target_row['student_name'])
                e_no = st.number_input("Class No", value=int(target_row['class_no']))
                c_save, c_del = st.columns([1,1])
                if c_save.form_submit_button("💾 Save"):
                    update_student_details(e_id, e_name, e_no); st.rerun()
                if c_del.form_submit_button("🗑️ Delete"):
                    delete_single_student(e_id); st.rerun()
    with t4:
        roster_all = get_class_roster(level, room, only_active=False) 
        if not roster_all.empty:
            roster_all['lbl'] = roster_all.apply(lambda x: f"{x['class_no']}. {x['student_name']} (Status: {x['status']})", axis=1)
            status_target_lbl = st.selectbox("Select Student", roster_all['lbl'], key='status_sel')
            if status_target_lbl:
                target_row = roster_all[roster_all['lbl'] == status_target_lbl].iloc[0]
                target_id = target_row['student_id']
                current_status = target_row['status']
                new_status = st.selectbox("Set New Status", STUDENT_STATUSES, index=STUDENT_STATUSES.index(current_status))
                if st.button("Update Status", use_container_width=True):
                    ok, msg = update_student_status(target_id, new_status)
                    if ok: st.success(msg); time.sleep(1); st.rerun()
                    else: st.error(msg)
        else: st.warning("No students.")
    with t5:
        st.error("⚠️ DANGER ZONE")
        if st.button(f"Delete ALL in {level}/{room}"):
            delete_entire_roster(level, room); st.rerun()
    st.subheader("Class Roster Overview")
    curr = get_class_roster(level, room, only_active=False)
    if not curr.empty: st.dataframe(curr[['class_no','student_id','student_name', 'status']], hide_index=True, width="stretch")

def page_input_grades():
    st.title("📝 Class Record Input")
    subs_raw = get_teacher_subjects_full(st.session_state.user[0])
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
    if roster.empty: st.warning("No **Active** students."); return
    sh = get_db_connection()
    ws = sh.worksheet("Grades")
    recs = ws.get_all_records()
    graded_ids = []
    for r in recs:
        if r['subject'] == subj and r['quarter'] == q and r['school_year'] == yr:
            graded_ids.append(str(r['student_id']))
    total_students = len(roster)
    roster['student_id_clean'] = roster['student_id'].astype(str).str.replace(r'\.0$', '', regex=True)
    done_count = sum(1 for sid in roster['student_id_clean'] if sid in graded_ids)
    prog_val = done_count / total_students if total_students > 0 else 0
    st.progress(prog_val, text=f"📊 Progress: {done_count} / {total_students}")
    roster['lbl'] = roster.apply(lambda x: f"{x['class_no']}. {x['student_name']} ({'✅' if x['student_id_clean'] in graded_ids else '❌'})", axis=1)
    sel_lbl = st.selectbox("Choose:", roster['lbl'])
    sel_row = roster[roster['lbl'] == sel_lbl].iloc[0]
    s_id, s_name = sel_row['student_id_clean'], sel_row['student_name']
    st.markdown("---")
    left, right = st.columns([1, 2.5])
    with left:
        st.markdown(f"**{s_name}**")
        photo_bytes = get_student_photo(s_id)
        if photo_bytes: st.image(Image.open(io.BytesIO(photo_bytes)), width=150)
        else: st.image("https://cdn-icons-png.flaticon.com/512/3237/3237472.png", width=150)
        with st.popover("📷 Upload Photo"):
            stu_pic = st.file_uploader("Upload", type=['jpg','png'], key="stu_up")
            if stu_pic: update_student_pic(s_id, stu_pic.getvalue()); st.rerun()
    with right:
        ex = get_grade_record(s_id, subj, q, yr)
        is_locked = False
        if ex:
            st.info(f"Existing Total Score: {ex[4]:.1f} / 50")
            is_locked = True
            if st.checkbox("🔓 Unlock to Edit", value=False): is_locked = False
        st.subheader("📊 Score Calculator")
        with st.form("cal_form"):
            c1, c2, c3, c4 = st.columns([2.5, 1.2, 1.2, 1.1])
            c1.markdown("**Task**"); c2.markdown("**Score**"); c3.markdown("**Max**"); c4.markdown("**Weight**")
            # T1
            c1, c2, c3, c4 = st.columns([2.5, 1.2, 1.2, 1.1])
            c1.text_input("L1", "Test 1", key="l1", label_visibility="collapsed", disabled=is_locked)
            r1 = c2.number_input("R1", 0, 999, key="r1", label_visibility="collapsed", disabled=is_locked)
            m1 = c3.number_input("M1", 1, 999, value=100, key="m1", label_visibility="collapsed", disabled=is_locked)
            f1 = min((r1/m1)*10 if m1>0 else 0, 10.0)
            c4.metric("10", fmt_score(f1), label_visibility="collapsed")
            # T2
            c1, c2, c3, c4 = st.columns([2.5, 1.2, 1.2, 1.1])
            c1.text_input("L2", "Test 2", key="l2", label_visibility="collapsed", disabled=is_locked)
            r2 = c2.number_input("R2", 0, 999, key="r2", label_visibility="collapsed", disabled=is_locked)
            m2 = c3.number_input("M2", 1, 999, value=100, key="m2", label_visibility="collapsed", disabled=is_locked)
            f2 = min((r2/m2)*10 if m2>0 else 0, 10.0)
            c4.metric("10", fmt_score(f2), label_visibility="collapsed")
            # T3
            c1, c2, c3, c4 = st.columns([2.5, 1.2, 1.2, 1.1])
            c1.text_input("L3", "Test 3", key="l3", label_visibility="collapsed", disabled=is_locked)
            r3 = c2.number_input("R3", 0, 999, key="r3", label_visibility="collapsed", disabled=is_locked)
            m3 = c3.number_input("M3", 1, 999, value=100, key="m3", label_visibility="collapsed", disabled=is_locked)
            f3 = min((r3/m3)*10 if m3>0 else 0, 10.0)
            c4.metric("10", fmt_score(f3), label_visibility="collapsed")
            # Final
            c1, c2, c3, c4 = st.columns([2.5, 1.2, 1.2, 1.1])
            c1.text_input("L4", "Final", key="l4", label_visibility="collapsed", disabled=is_locked)
            rf = c2.number_input("RF", 0, 999, key="rf", label_visibility="collapsed", disabled=is_locked)
            mf = c3.number_input("MF", 1, 999, value=50, key="mf", label_visibility="collapsed", disabled=is_locked)
            ff = min((rf/mf)*20 if mf>0 else 0, 20.0)
            c4.metric("20", fmt_score(ff), label_visibility="collapsed")
            total = f1+f2+f3+ff
            st.markdown("---")
            st.markdown(f"### 🏆 Total: {total:.1f} / 50")
            if st.form_submit_button("💾 Save", use_container_width=True, disabled=is_locked):
                save_grade({"s_id":s_id,"subj":subj,"q":q,"year":yr,"t1":f1,"t2":f2,"t3":f3,"final":ff,"total":total,"teacher":st.session_state.user[0]})
                st.toast("Saved!"); time.sleep(1); st.rerun()

def page_gradebook():
    st.title("📊 Gradebook")
    subs_raw = get_teacher_subjects_full(st.session_state.user[0])
    subjects = [s[1] for s in subs_raw]
    if not subjects: st.warning("No subjects"); return
    c1,c2,c3,c4 = st.columns(4)
    s = c1.selectbox("Subject", subjects)
    l = c2.selectbox("Level", ["M1","M2","M3","M4","M5","M6"])
    r = c3.selectbox("Room", [str(i) for i in range(1,16)])
    q = c4.selectbox("Quarter", ["Q1","Q2","Q3","Q4"])
    sh = get_db_connection()
    students = sh.worksheet("Students").get_all_records()
    grades = sh.worksheet("Grades").get_all_records()
    data = []
    for stu in students:
        if stu['grade_level'] == l and str(stu['room']) == str(r) and stu['status'] == 'Active':
            row = {'class_no': stu['class_no'], 'student_id': str(stu['student_id']), 'student_name': stu['student_name'], 'test1': 0, 'test2': 0, 'test3': 0, 'final_score': 0, 'total_score': 0}
            for g in grades:
                if (str(g['student_id']) == str(stu['student_id']) and g['subject'] == s and g['quarter'] == q):
                    row['test1'] = g['test1']; row['test2'] = g['test2']; row['test3'] = g['test3']; row['final_score'] = g['final_score']; row['total_score'] = g['total_score']
            data.append(row)
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values('class_no')
        st.dataframe(df.style.format(precision=1), width="stretch")
        st.download_button("⬇️ Excel", df.to_csv(index=False), f"gradebook_{s}_{q}.csv", "text/csv")

def page_student_record_teacher_view():
    st.title("👤 Student Record")
    s_search = st.text_input("Enter Student ID")
    if s_search:
        details = get_student_details(str(s_search).strip())
        if details:
            name, lvl, rm, photo, status = details
            c1, c2 = st.columns([1, 3])
            with c1:
                if photo: st.image(Image.open(io.BytesIO(photo)), width=180)
                else: st.image("https://cdn-icons-png.flaticon.com/512/3237/3237472.png", width=180)
                st.markdown(f"### {name}"); st.caption(f"ID: {s_search}"); st.info(f"Class: {lvl}/{rm} ({status})")
            with c2:
                df = get_student_grades_for_teacher_view(s_search, st.session_state.user[0])
                if not df.empty: display_academic_transcript(df)
                else: st.warning("No grades recorded by you.")
        else: st.error("Not found.")

def display_academic_transcript(df):
    # Create the pivot table
    pivot = df.pivot_table(index=['school_year', 'subject'], columns='quarter', values='total_score', aggfunc='first').reset_index()
    
    # Ensure all quarters exist
    for q in ['Q1', 'Q2', 'Q3', 'Q4']:
        if q not in pivot.columns: pivot[q] = 0.0
    
    # Calculate Semesters
    pivot['Sem 1'] = pivot['Q1'].fillna(0) + pivot['Q2'].fillna(0)
    pivot['Sem 2'] = pivot['Q3'].fillna(0) + pivot['Q4'].fillna(0)
    
    # Calculate GPAs
    pivot['GPA S1'] = pivot['Sem 1'].apply(get_grade_point)
    pivot['GPA S2'] = pivot['Sem 2'].apply(get_grade_point)

    # Display per year
    for yr in pivot['school_year'].unique():
        st.markdown(f"#### 🗓️ {yr}")
        # Filter for the specific year
        d = pivot[pivot['school_year'] == yr][['subject', 'Q1', 'Q2', 'Sem 1', 'GPA S1', 'Q3', 'Q4', 'Sem 2', 'GPA S2']]
        
        # --- THE FIX IS HERE (Unique Names) ---
        d.columns = ['Subject', 'Q1 (50)', 'Q2 (50)', 'Sem 1 Total', 'S1 Grade', 'Q3 (50)', 'Q4 (50)', 'Sem 2 Total', 'S2 Grade']
        
        # Show the table
        st.dataframe(d.style.format(precision=1), hide_index=True, width="stretch")


def page_student_portal_grades():
    s_data = st.session_state.user
    st.title("📜 My Academic Record"); st.info(f"Welcome, {s_data[1]}.")
    df = get_student_full_report(s_data[0])
    if not df.empty: display_academic_transcript(df)
    else: st.warning("No grades found.")

def page_student_settings():
    st.title("⚙️ Settings")
    with st.form("pwd_change"):
        p1 = st.text_input("New Password", type="password")
        p2 = st.text_input("Confirm New Password", type="password")
        if st.form_submit_button("Update Password"):
            if p1 and p2 and p1 == p2:
                change_student_password(st.session_state.user[0], p1)
                st.success("✅ Password updated!")
            else: st.warning("Check inputs.")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    init_db()

if not st.session_state.logged_in: login_screen()
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