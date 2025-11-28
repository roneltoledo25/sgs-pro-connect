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
STUDENT_STATUSES = ["Active", "Transferred", "Dropped Out", "Graduate", "Deleted"]

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_db_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        json_str = st.secrets["gcp"]["service_account_json"]
        creds_dict = json.loads(json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"❌ Database Connection Error: {e}")
        st.stop()

def init_db():
    try:
        sh = get_db_connection()
        existing_titles = [w.title for w in sh.worksheets()]
        if "Users" not in existing_titles:
            ws = sh.add_worksheet("Users", 100, 10)
            ws.append_row(["username", "password", "role", "profile_pic"])
            ws.append_row(["admin", "admin123", "Admin", ""])
        if "Subjects" not in existing_titles:
            ws = sh.add_worksheet("Subjects", 100, 5)
            ws.append_row(["id", "teacher_username", "subject_name"])
        if "Students" not in existing_titles:
            ws = sh.add_worksheet("Students", 100, 10)
            ws.append_row(["student_id", "student_name", "class_no", "grade_level", "room", "photo", "password", "status"])
        if "Grades" not in existing_titles:
            ws = sh.add_worksheet("Grades", 100, 15)
            ws.append_row(["id", "student_id", "subject", "quarter", "school_year", "test1", "test2", "test3", "final_score", "total_score", "recorded_by", "timestamp"])
        if "Tasks" not in existing_titles:
            ws = sh.add_worksheet("Tasks", 100, 12)
            ws.append_row(["uid", "student_id", "subject", "quarter", "school_year", "test_name", "t1", "t2", "t3", "t4", "t5", "raw_total"])
    except Exception as e:
        st.error(f"DB Init Error: {e}")

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
    try:
        img = Image.open(io.BytesIO(img_bytes))
        img.thumbnail((150, 150))
        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=60)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except: return ""

def base64_to_image(b64_str):
    if not b64_str: return None
    try: return base64.b64decode(b64_str)
    except: return None

# --- BACKEND FUNCTIONS WITH CACHING ---

@st.cache_data(ttl=5)
def fetch_all_records(sheet_name):
    sh = get_db_connection()
    return sh.worksheet(sheet_name).get_all_records()

def clear_cache():
    st.cache_data.clear()

def login_staff(username, password):
    records = fetch_all_records("Users")
    for row in records:
        if str(row['username']) == str(username) and str(row['password']) == str(password):
            return (row['username'], row['password'], row['role'], base64_to_image(row['profile_pic']))
    return None

def login_student(student_id, password):
    records = fetch_all_records("Students")
    s_id_in = str(student_id).strip()
    for row in records:
        if str(row['student_id']).strip() == s_id_in:
            if row.get('status', 'Active') == 'Deleted': return None
            db_pass = str(row['password'])
            is_valid = False
            if not db_pass and str(password) == s_id_in: is_valid = True
            elif str(password) == db_pass: is_valid = True
            if is_valid:
                return (row['student_id'], row['student_name'], row['password'], base64_to_image(row['photo']), row.get('status','Active'))
    return None

def change_student_password(s_id, new_pass):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell: 
        ws.update_cell(cell.row, 7, new_pass)
        clear_cache()

def register_user(username, password, code):
    if code != SCHOOL_CODE: return False, "❌ Invalid School Code!"
    sh = get_db_connection()
    ws = sh.worksheet("Users")
    if ws.find(username): return False, "⚠️ Username taken"
    ws.append_row([username, password, 'Teacher', ""])
    clear_cache()
    return True, "✅ Success"

# --- ADMIN FUNCTIONS ---
def get_admin_stats():
    users = fetch_all_records("Users")
    studs = fetch_all_records("Students")
    subs = fetch_all_records("Subjects")
    active = sum(1 for s in studs if s.get('status') == 'Active')
    dropped = sum(1 for s in studs if s.get('status') == 'Dropped Out')
    transferred = sum(1 for s in studs if s.get('status') == 'Transferred')
    deleted = sum(1 for s in studs if s.get('status') == 'Deleted')
    return len(users), active, dropped, transferred, deleted, len(subs)

def get_all_teachers_with_counts():
    users = fetch_all_records("Users")
    subs = fetch_all_records("Subjects")
    data = []
    for u in users:
        if u['role'] == 'Teacher':
            count = sum(1 for s in subs if s['teacher_username'] == u['username'])
            data.append({'username': u['username'], 'password': u['password'], 'subject_count': count})
    return pd.DataFrame(data).astype(str)

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
    clear_cache()

def admin_reset_teacher_password(username, new_pass):
    sh = get_db_connection()
    ws = sh.worksheet("Users")
    cell = ws.find(username)
    if cell: 
        ws.update_cell(cell.row, 2, new_pass)
        clear_cache()

def get_all_students_admin(include_deleted=False):
    data = fetch_all_records("Students")
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.astype(str)
        if not include_deleted:
            df = df[df['status'] != 'Deleted']
    return df

def delete_student_admin(s_id):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell: ws.delete_rows(cell.row)
    clear_cache()

def admin_restore_student(s_id):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell:
        ws.update_cell(cell.row, 8, "Active")
        clear_cache()
        return True
    return False

def admin_reset_student_password(s_id, new_pass):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell: 
        ws.update_cell(cell.row, 7, new_pass)
        clear_cache()

# --- GENERAL FUNCTIONS ---
def update_teacher_pic(username, image_bytes):
    sh = get_db_connection()
    ws = sh.worksheet("Users")
    cell = ws.find(username)
    if cell: 
        ws.update_cell(cell.row, 4, image_to_base64(image_bytes))
        clear_cache()

def update_student_pic(student_id, image_bytes):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(student_id))
    if cell: 
        ws.update_cell(cell.row, 6, image_to_base64(image_bytes))
        clear_cache()

def get_teacher_data(username):
    user = login_staff(username, "") 
    if user: return user[3] 
    return None

def get_student_photo(student_id):
    records = fetch_all_records("Students")
    for r in records:
        if str(r['student_id']) == str(student_id):
            return base64_to_image(r['photo'])
    return None

def get_student_details(student_id):
    records = fetch_all_records("Students")
    for r in records:
        if str(r['student_id']) == str(student_id):
            return (r['student_name'], r['grade_level'], r['room'], base64_to_image(r['photo']), r.get('status','Active'))
    return None

def get_next_class_no(level, room):
    records = fetch_all_records("Students")
    max_no = 0
    for r in records:
        if r['grade_level'] == level and str(r['room']) == str(room) and r.get('status') != 'Deleted':
            if int(r['class_no']) > max_no: max_no = int(r['class_no'])
    return max_no + 1

def add_single_student(s_id, name, no, level, room, status="Active"):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    try:
        if ws.find(str(s_id)): return False, f"⚠️ Student ID {s_id} already exists!"
    except: pass
    ws.append_row([str(s_id), name, no, level, room, "", "", status])
    clear_cache()
    return True, f"✅ Added {name}"

def update_student_details(s_id, new_name, new_no, new_status):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell:
        ws.update_cell(cell.row, 2, new_name)
        ws.update_cell(cell.row, 3, new_no)
        ws.update_cell(cell.row, 8, new_status)
        clear_cache()
        return True, "Updated"
    return False, "Not found"

def update_student_status(s_id, new_status):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell:
        ws.update_cell(cell.row, 8, new_status)
        clear_cache()
        return True, f"Status updated to {new_status}"
    return False, "Error"

def delete_single_student(s_id):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    cell = ws.find(str(s_id))
    if cell:
        ws.update_cell(cell.row, 8, "Deleted")
        clear_cache()
        return True, "Moved to Bin"
    return False, "Error"

def soft_delete_class_roster(level, room):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    all_data = ws.get_all_records()
    new_rows = []
    new_rows.append(["student_id", "student_name", "class_no", "grade_level", "room", "photo", "password", "status"])
    count = 0
    for r in all_data:
        stat = r.get('status', 'Active')
        if r['grade_level'] == level and str(r['room']) == str(room):
            stat = "Deleted"
            count += 1
        new_rows.append([r['student_id'], r['student_name'], r['class_no'], r['grade_level'], r['room'], r['photo'], r['password'], stat])
    ws.clear()
    ws.append_rows(new_rows)
    clear_cache()
    return True, f"Moved {count} students to Bin"

def promote_students(from_lvl, from_rm, to_lvl, to_rm):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    all_data = ws.get_all_records()
    new_rows = []
    new_rows.append(["student_id", "student_name", "class_no", "grade_level", "room", "photo", "password", "status"])
    count = 0
    for r in all_data:
        lvl = r['grade_level']
        rm = str(r['room'])
        stat = r.get('status', 'Active')
        if lvl == from_lvl and rm == str(from_rm) and stat == 'Active':
            lvl = to_lvl
            rm = to_rm
            count += 1
        new_rows.append([r['student_id'], r['student_name'], r['class_no'], lvl, rm, r['photo'], r['password'], stat])
    ws.clear()
    ws.append_rows(new_rows)
    clear_cache()
    return True, f"Promoted {count} students"

def upload_roster(df, level, room):
    sh = get_db_connection()
    ws = sh.worksheet("Students")
    existing_ids = [str(r['student_id']) for r in ws.get_all_records()]
    added = 0
    errors = []
    rows_to_add = []
    current_max = 0
    all_recs = ws.get_all_records()
    for r in all_recs:
        if r['grade_level'] == level and str(r['room']) == str(room) and r.get('status') != 'Deleted':
             if int(r['class_no']) > current_max: current_max = int(r['class_no'])
    current_number = current_max + 1
    for index, row in df.iterrows():
        s_id = str(row['ID']).strip()
        if s_id.endswith('.0'): s_id = s_id[:-2]
        name = str(row['Name']).strip()
        if s_id in existing_ids:
            errors.append(f"Skipped {s_id} (Duplicate)")
            continue
        rows_to_add.append([s_id, name, current_number, level, room, "", "", "Active"])
        existing_ids.append(s_id)
        current_number += 1
        added += 1
    if rows_to_add: ws.append_rows(rows_to_add)
    clear_cache()
    return True, f"✅ Uploaded {added}", errors

def get_class_roster(level, room, only_active=False):
    records = fetch_all_records("Students")
    filtered = []
    for r in records:
        if r['grade_level'] == level and str(r['room']) == str(room):
            stat = r.get('status', 'Active')
            if stat == 'Deleted': continue
            if only_active and stat != 'Active': continue
            filtered.append(r)
    df = pd.DataFrame(filtered)
    if not df.empty:
        df = df.astype(str)
        df['class_no'] = pd.to_numeric(df['class_no'])
        df = df.sort_values('class_no')
        if 'status' not in df.columns: df['status'] = 'Active'
    return df

def get_all_active_students_list():
    records = fetch_all_records("Students")
    res = []
    for r in records:
        if r.get('status') == 'Active':
            res.append(r)
    return pd.DataFrame(res)

def get_teacher_subjects_full(teacher):
    records = fetch_all_records("Subjects")
    res = []
    for r in records:
        if r['teacher_username'] == teacher:
            res.append((r['id'], r['subject_name']))
    return res

def get_subject_student_count(subject_name):
    grades = fetch_all_records("Grades")
    count = sum(1 for g in grades if g['subject'] == subject_name)
    return count

def add_subject(teacher, subject):
    sh = get_db_connection()
    ws = sh.worksheet("Subjects")
    records = ws.get_all_records()
    for r in records:
        if r['teacher_username'] == teacher and r['subject_name'] == subject:
            return False, "⚠️ You already have this subject."
    new_id = int(time.time())
    ws.append_row([new_id, teacher, subject])
    clear_cache()
    return True, "Added"

def delete_subject(sub_id):
    sh = get_db_connection()
    ws = sh.worksheet("Subjects")
    records = ws.get_all_records()
    for i, r in enumerate(records):
        if str(r['id']) == str(sub_id):
            ws.delete_rows(i + 2)
            clear_cache()
            return

def update_subject(sub_id, new_name):
    sh = get_db_connection()
    ws = sh.worksheet("Subjects")
    records = ws.get_all_records()
    for i, r in enumerate(records):
        if str(r['id']) == str(sub_id):
            ws.update_cell(i + 2, 3, new_name)
            clear_cache()
            return True
    return False

def fetch_task_records(subject, quarter, year, test_name):
    records = fetch_all_records("Tasks")
    res = {}
    for r in records:
        if r['subject'] == subject and r['quarter'] == quarter and r['school_year'] == year and r['test_name'] == test_name:
            res[str(r['student_id'])] = r
    return res

def save_batch_tasks_and_grades(subject, quarter, year, test_name, task_df, max_score, weight, teacher):
    sh = get_db_connection()
    ws_tasks = sh.worksheet("Tasks")
    ws_grades = sh.worksheet("Grades")
    all_tasks = ws_tasks.get_all_records()
    keep_tasks = []
    for t in all_tasks:
        if not (t['subject'] == subject and t['quarter'] == quarter and t['school_year'] == year and t['test_name'] == test_name):
            keep_tasks.append(t)
    
    new_task_rows = []
    grade_updates = {}
    
    for idx, row in task_df.iterrows():
        sid = str(row['ID'])
        t1 = float(row.get('Task 1', 0))
        t2 = float(row.get('Task 2', 0))
        t3 = float(row.get('Task 3', 0))
        t4 = float(row.get('Task 4', 0))
        t5 = float(row.get('Task 5', 0))
        raw_total = t1+t2+t3+t4+t5
        
        weighted = 0.0
        if max_score > 0:
            weighted = (raw_total / max_score) * weight
            if weighted > weight: weighted = weight
            
        grade_updates[sid] = weighted
        uid = f"{sid}_{subject}_{quarter}_{year}_{test_name}"
        new_task_rows.append([uid, sid, subject, quarter, year, test_name, t1, t2, t3, t4, t5, raw_total])

    final_task_data = []
    final_task_data.append(["uid", "student_id", "subject", "quarter", "school_year", "test_name", "t1", "t2", "t3", "t4", "t5", "raw_total"])
    for k in keep_tasks: final_task_data.append(list(k.values()))
    final_task_data.extend(new_task_rows)
    
    ws_tasks.clear()
    ws_tasks.append_rows(final_task_data)
    
    all_grades = ws_grades.get_all_records()
    updated_grades = []
    updated_grades.append(["id", "student_id", "subject", "quarter", "school_year", "test1", "test2", "test3", "final_score", "total_score", "recorded_by", "timestamp"])
    processed_sids = []
    
    for g in all_grades:
        if g['subject'] == subject and g['quarter'] == quarter and g['school_year'] == year:
            sid = str(g['student_id'])
            if sid in grade_updates:
                new_val = grade_updates[sid]
                if test_name == "Test 1": g['test1'] = new_val
                elif test_name == "Test 2": g['test2'] = new_val
                elif test_name == "Test 3": g['test3'] = new_val
                g['total_score'] = float(g['test1']) + float(g['test2']) + float(g['test3']) + float(g['final_score'])
                g['recorded_by'] = teacher
                g['timestamp'] = str(datetime.datetime.now())
                processed_sids.append(sid)
        updated_grades.append(list(g.values()))
        
    for sid, score in grade_updates.items():
        if sid not in processed_sids:
            new_row = {
                "id": int(time.time()) + int(sid), "student_id": sid, "subject": subject, "quarter": quarter, "school_year": year,
                "test1": 0, "test2": 0, "test3": 0, "final_score": 0, "total_score": 0, "recorded_by": teacher, "timestamp": str(datetime.datetime.now())
            }
            if test_name == "Test 1": new_row['test1'] = score
            elif test_name == "Test 2": new_row['test2'] = score
            elif test_name == "Test 3": new_row['test3'] = score
            new_row['total_score'] = score
            updated_grades.append(list(new_row.values()))
            
    ws_grades.clear()
    ws_grades.append_rows(updated_grades)
    clear_cache()
    return True, "Batch Save Successful"

def save_final_exam_batch(subject, quarter, year, grade_df, max_score, teacher):
    sh = get_db_connection()
    ws_grades = sh.worksheet("Grades")
    all_grades = ws_grades.get_all_records()
    
    grade_updates = {}
    for idx, row in grade_df.iterrows():
        sid = str(row['ID'])
        raw = float(row.get('Final Score', 0))
        weighted = 0.0
        if max_score > 0:
            weighted = (raw / max_score) * 20.0 
            if weighted > 20.0: weighted = 20.0
        grade_updates[sid] = weighted
        
    updated_grades = []
    updated_grades.append(["id", "student_id", "subject", "quarter", "school_year", "test1", "test2", "test3", "final_score", "total_score", "recorded_by", "timestamp"])
    processed_sids = []
    
    for g in all_grades:
        if g['subject'] == subject and g['quarter'] == quarter and g['school_year'] == year:
            sid = str(g['student_id'])
            if sid in grade_updates:
                g['final_score'] = grade_updates[sid]
                g['total_score'] = float(g['test1']) + float(g['test2']) + float(g['test3']) + float(g['final_score'])
                g['recorded_by'] = teacher
                g['timestamp'] = str(datetime.datetime.now())
                processed_sids.append(sid)
        updated_grades.append(list(g.values()))
        
    for sid, score in grade_updates.items():
        if sid not in processed_sids:
            new_row = {
                "id": int(time.time()) + int(sid), "student_id": sid, "subject": subject, "quarter": quarter, "school_year": year,
                "test1": 0, "test2": 0, "test3": 0, "final_score": score, "total_score": score, "recorded_by": teacher, "timestamp": str(datetime.datetime.now())
            }
            updated_grades.append(list(new_row.values()))
            
    ws_grades.clear()
    ws_grades.append_rows(updated_grades)
    clear_cache()
    return True

def get_student_grades_for_teacher_view(student_id, teacher_username):
    records = fetch_all_records("Grades")
    data = []
    for r in records:
        if str(r['student_id']) == str(student_id) and r['recorded_by'] == teacher_username:
            data.append(r)
    return pd.DataFrame(data)

def get_student_full_report(student_id):
    records = fetch_all_records("Grades")
    data = []
    for r in records:
        if str(r['student_id']) == str(student_id):
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
                    else: st.error("Invalid ID or Password, or account not Active.")

def sidebar_menu():
    if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0
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
                ukey = st.session_state.uploader_key
                up = st.file_uploader("Up", type=['jpg','png'], label_visibility="collapsed", key=f"t_up_{ukey}")
                if up: 
                    img_bytes = up.getvalue()
                    update_teacher_pic(username, img_bytes)
                    new_user_data = (user_data[0], user_data[1], user_data[2], img_bytes)
                    st.session_state.user = new_user_data
                    st.toast("✅ Photo Updated!")
                    st.session_state.uploader_key += 1
                    time.sleep(1.0); st.rerun()
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

# --- PAGE FUNCTIONS ---

def page_admin_dashboard():
    st.title("🛡️ Admin Dashboard")
    tot_t, act, drp, trf, dele, tot_sub = get_admin_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Teachers", tot_t)
    c2.metric("Total Subjects", tot_sub)
    st.markdown("### 🎓 Student Status Overview")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("✅ Active", act)
    k2.metric("🔁 Transferred", trf)
    k3.metric("❌ Dropped Out", drp)
    k4.metric("🗑️ Deleted (Bin)", dele)

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
    tab_list, tab_restore = st.tabs(["📋 Active List", "♻️ Restore Deleted"])
    with tab_list:
        df = get_all_students_admin(include_deleted=False)
        search = st.text_input("🔍 Search Student ID or Name", key="adm_search")
        if search and not df.empty:
            df = df[df['student_name'].str.contains(search, case=False) | df['student_id'].astype(str).str.contains(search)]
        st.dataframe(df, width=1000, hide_index=True)
        st.markdown("### ✏️ Edit Student Account")
        c1, c2, c3 = st.columns([1,2,1])
        target_id = c1.text_input("Enter ID to Edit")
        if target_id:
            with c2.form("admin_stu_edit"):
                new_pass = st.text_input("Set New Password")
                if st.form_submit_button("Reset Password"):
                    admin_reset_student_password(target_id, new_pass)
                    st.success(f"Password for {target_id} reset.")
            if c3.button("🗑️ Hard Delete", key="del_stu_adm"):
                delete_student_admin(target_id)
                st.warning(f"Student {target_id} permanently deleted."); time.sleep(1); st.rerun()
    with tab_restore:
        st.markdown("### 🗑️ Recycle Bin (Deleted Students)")
        df_del = get_all_students_admin(include_deleted=True)
        if not df_del.empty: df_del = df_del[df_del['status'] == 'Deleted']
        if not df_del.empty:
            st.dataframe(df_del, width=1000, hide_index=True)
            res_id = st.selectbox("Select Student to Restore", df_del['student_id'].astype(str) + " - " + df_del['student_name'])
            if st.button("♻️ Restore Selected"):
                sid_only = res_id.split(" - ")[0]
                if admin_restore_student(sid_only):
                    st.success(f"Student {sid_only} restored to Active!")
                    time.sleep(1.5); st.rerun()
        else: st.info("Bin is empty.")

def page_dashboard():
    st.title("📊 Teacher Dashboard")
    recs = fetch_all_records("Students")
    active_sys = sum(1 for r in recs if r.get('status') == 'Active')
    c_sel1, c_sel2 = st.columns(2)
    with c_sel1: lvl = st.selectbox("Select Level", ["M1","M2","M3","M4","M5","M6"])
    with c_sel2: rm = st.selectbox("Select Room", [str(i) for i in range(1,16)])
    class_active = sum(1 for r in recs if r['grade_level'] == lvl and str(r['room']) == str(rm) and r.get('status') == 'Active')
    m1, m2 = st.columns(2)
    m1.metric("Active Students (System)", active_sys)
    m2.metric(f"Active in {lvl}/{rm}", class_active)
    st.markdown("---")
    st.subheader("📚 My Subjects Overview")
    with st.expander("➕ Add New Subject"):
        with st.form("add_sub_form"):
            new_s = st.text_input("Subject Name")
            if st.form_submit_button("Add Subject"):
                ok, msg = add_subject(st.session_state.user[0], new_s)
                if ok: st.rerun()
                else: st.error(msg)
    subjects = get_teacher_subjects_full(st.session_state.user[0])
    if subjects:
        sub_data = []
        for sub_id, sub_name in subjects:
            count = get_subject_student_count(sub_name)
            sub_data.append({"Subject": sub_name, "Students Graded": count})
        st.dataframe(pd.DataFrame(sub_data), width=1000, hide_index=True)
        st.markdown("### Manage Subjects")
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
    t1, t2, t3, t4, t5 = st.tabs(["📤 Bulk Upload", "➕ Manual Add", "✏️ Edit / Status", "🚀 Promote / Transfer", "🗑️ Reset Class"])
    with t1:
        st.info("ℹ️ Note: Uploaded students are automatically set to 'Active'.")
        csv = pd.DataFrame({"ID":["10101","10102"], "Name":["Student A","Student B"]}).to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Template", csv, "template.csv", "text/csv")
        up_file = st.file_uploader("Excel/CSV", type=['xlsx','csv'], key="roster_uploader")
        if up_file:
            if st.button("Upload"):
                try:
                    df = pd.read_csv(up_file) if up_file.name.endswith('.csv') else pd.read_excel(up_file)
                    ok, msg, errs = upload_roster(df, level, room)
                    if ok: st.success(msg)
                    if errs: st.error(f"{len(errs)} Errors")
                    time.sleep(1.5); st.rerun()
                except Exception as e: st.error(str(e))
    with t2:
        next_no = get_next_class_no(level, room)
        with st.form("manual_add"):
            c_a, c_b = st.columns([1,3])
            m_id = c_a.text_input("ID")
            m_name = c_b.text_input("Name")
            c_c, c_d = st.columns([1,1])
            m_no = c_c.number_input("No", value=next_no, disabled=True)
            m_stat = c_d.selectbox("Status", ["Active", "Dropped Out", "Transferred", "Graduate"])
            if st.form_submit_button("✅ Add Student"):
                if m_id and m_name:
                    ok, msg = add_single_student(m_id, m_name, int(m_no), level, room, m_stat)
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
                c_edit_1, c_edit_2 = st.columns(2)
                e_no = c_edit_1.number_input("Class No", value=int(target_row['class_no']))
                curr_stat = target_row.get('status', 'Active')
                valid_opts = [s for s in STUDENT_STATUSES if s != 'Deleted']
                idx = valid_opts.index(curr_stat) if curr_stat in valid_opts else 0
                e_stat = c_edit_2.selectbox("Status", valid_opts, index=idx)
                c_save, c_del = st.columns([1,1])
                if c_save.form_submit_button("💾 Save Changes"):
                    update_student_details(e_id, e_name, e_no, e_stat)
                    st.toast("Updated!"); time.sleep(1); st.rerun()
                if c_del.form_submit_button("🗑️ Delete (Soft)"):
                    delete_single_student(e_id)
                    st.warning("Moved to Bin (Admin can restore)"); time.sleep(1); st.rerun()
        else: st.warning("No students.")
    with t4:
        st.markdown(f"### 🚀 Transfer Active Students from {level}/{room}")
        c_to1, c_to2 = st.columns(2)
        to_lvl = c_to1.selectbox("To Level", ["M1","M2","M3","M4","M5","M6"], key="to_lvl")
        to_rm = c_to2.selectbox("To Room", [str(i) for i in range(1,16)], key="to_rm")
        st.warning(f"⚠️ This will move ALL 'Active' students from **{level}/{room}** to **{to_lvl}/{to_rm}**.")
        if st.button("🚀 Execute Transfer"):
            ok, msg = promote_students(level, room, to_lvl, to_rm)
            if ok: st.success(msg); time.sleep(2); st.rerun()
            else: st.error(msg)
    with t5:
        st.error("⚠️ DANGER ZONE")
        st.markdown(f"This will move **ALL** students in **{level}/{room}** to the Recycle Bin.")
        if st.button(f"🗑️ Delete Class {level}/{room}"):
            ok, msg = soft_delete_class_roster(level, room)
            if ok: st.success(msg); time.sleep(1.5); st.rerun()
    curr = get_class_roster(level, room, only_active=False)
    if not curr.empty:
        def highlight_status(val):
            if val == 'Active': return 'color: green; font-weight: bold'
            if val == 'Deleted': return 'color: gray; text-decoration: line-through'
            return 'color: red; font-weight: bold'
        st.markdown("### 📋 Class List")
        st.dataframe(curr[['class_no','student_id','student_name', 'status']].style.map(highlight_status, subset=['status']), hide_index=True, width=1000)

def page_input_grades():
    st.title("📝 Class Record Input")
    if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

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
    if roster.empty: st.warning("No Active students."); return

    # --- NEW UI LAYOUT ---
    t_tabs = st.tabs(["Test 1 (Tasks)", "Test 2 (Tasks)", "Test 3 (Tasks)", "Final Exam", "Bulk Upload"])
    
    # Helper for Task Tabs
    def render_task_tab(test_name, weight):
        st.markdown(f"### 📊 {test_name} - Detailed Input")
        max_score = st.number_input(f"Max Raw Score for {test_name} (Sum of Tasks)", min_value=1.0, value=50.0, key=f"max_{test_name}")
        st.info(f"Scores will be converted to weight: **{weight}%**")
        
        # 1. Fetch Existing Data
        existing_tasks = fetch_task_records(subj, q, yr, test_name)
        
        # 2. Build Dataframe for Editor
        editor_data = []
        for idx, row in roster.iterrows():
            sid = str(row['student_id'])
            name = row['student_name']
            no = row['class_no']
            
            # Defaults
            t1, t2, t3, t4, t5 = 0.0, 0.0, 0.0, 0.0, 0.0
            if sid in existing_tasks:
                r = existing_tasks[sid]
                t1, t2, t3, t4, t5 = r['t1'], r['t2'], r['t3'], r['t4'], r['t5']
            
            raw_calc = t1+t2+t3+t4+t5
            weight_calc = (raw_calc / max_score) * weight if max_score else 0.0
            
            editor_data.append({
                "No": no, "ID": sid, "Name": name,
                "Task 1": t1, "Task 2": t2, "Task 3": t3, "Task 4": t4, "Task 5": t5,
                "Total": raw_calc, "Weighted": weight_calc
            })
            
        df_editor = pd.DataFrame(editor_data)
        
        # 3. Display Editor INSIDE FORM (FIX FOR BLINKING)
        with st.form(key=f"form_{test_name}"):
            edited_df = st.data_editor(
                df_editor, 
                hide_index=True,
                column_config={
                    "No": st.column_config.NumberColumn(disabled=True),
                    "ID": st.column_config.TextColumn(disabled=True),
                    "Name": st.column_config.TextColumn(disabled=True),
                    "Total": st.column_config.NumberColumn(disabled=True),
                    "Weighted": st.column_config.NumberColumn(disabled=True, format="%.2f")
                },
                width=1000,
                key=f"ed_{test_name}"
            )
            # 4. Save Button as FORM SUBMITTER
            if st.form_submit_button(f"💾 Batch Save {test_name}"):
                with st.spinner("Processing..."):
                    ok, msg = save_batch_tasks_and_grades(subj, q, yr, test_name, edited_df, max_score, weight, st.session_state.user[0])
                    if ok: st.success(msg); time.sleep(1.5); st.rerun()
                    else: st.error(msg)

    with t_tabs[0]: render_task_tab("Test 1", 10.0)
    with t_tabs[1]: render_task_tab("Test 2", 10.0)
    with t_tabs[2]: render_task_tab("Test 3", 10.0)
    
    with t_tabs[3]:
        st.markdown("### 🏁 Final Exam")
        max_final = st.number_input("Max Raw Score for Final", min_value=1.0, value=50.0, key="max_final")
        
        all_grades = fetch_all_records("Grades")
        final_data = []
        for idx, row in roster.iterrows():
            sid = str(row['student_id'])
            # Attempt to find current final score
            curr_score = 0.0
            # (Fetching specific grade is expensive loop here, assume 0 for speed or implement better fetch)
            # For simplicity in this batch view, we let them enter raw.
            # We display 0.0 default.
            
            # Simple calc for display (might be 0 if new)
            w_disp = (curr_score / max_final) * 20.0 if max_final else 0.0
            
            final_data.append({"No": row['class_no'], "ID": sid, "Name": row['student_name'], "Final Score": 0.0, "Weighted (20%)": 0.0})
            
        df_final = pd.DataFrame(final_data)
        
        # WRAP IN FORM
        with st.form("final_form"):
            edited_final = st.data_editor(
                df_final, hide_index=True,
                column_config={
                    "No": st.column_config.NumberColumn(disabled=True),
                    "ID": st.column_config.TextColumn(disabled=True),
                    "Name": st.column_config.TextColumn(disabled=True),
                    "Weighted (20%)": st.column_config.NumberColumn(disabled=True)
                }, width=1000, key="ed_final"
            )
            if st.form_submit_button("💾 Save Finals"):
                if save_final_exam_batch(subj, q, yr, edited_final, max_final, st.session_state.user[0]):
                    st.success("Finals Saved!"); time.sleep(1.5); st.rerun()

    with t_tabs[4]:
        st.markdown("### 📤 Legacy Bulk Upload")
        st.info("Use the tabs on the left for direct entry. Use this for offline Excel files.")
        
        col_sel1, col_sel2 = st.columns(2)
        upload_target = col_sel1.selectbox("Select Component", ["Test 1", "Test 2", "Test 3", "Final Exam"])
        target_weight = 20.0 if upload_target == "Final Exam" else 10.0
        max_raw = col_sel2.number_input(f"Total Raw for {upload_target}", min_value=1.0, value=50.0, key="bulk_max")
        
        template_df = roster[['class_no', 'student_id', 'student_name']].copy()
        template_df.columns = ['No', 'Student ID', 'Name']
        for i in range(1, 6): template_df[f'Task {i}'] = 0.0
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            template_df.to_excel(writer, index=False, sheet_name='TaskScores')
        excel_data = output.getvalue()
        
        st.download_button(f"⬇️ Download {upload_target} Template", data=excel_data, file_name="template.xlsx", mime="application/vnd.ms-excel")
        
        bulk_file = st.file_uploader(f"Upload {upload_target}", type=['xlsx'], key=f"up_{upload_target}")
        if bulk_file:
            if st.button(f"Process {upload_target}"):
                try:
                    df_upload = pd.read_excel(bulk_file)
                    df_upload = df_upload.rename(columns={"Student ID": "ID"})
                    save_batch_tasks_and_grades(subj, q, yr, upload_target, df_upload, max_raw, target_weight, st.session_state.user[0])
                    st.success("Uploaded!"); time.sleep(1.5); st.rerun()
                except Exception as e: st.error(f"Error: {e}")

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
    
    grades_all = fetch_all_records("Grades")
    students_all = fetch_all_records("Students")
    
    roster = []
    for stu in students_all:
        if stu['grade_level'] == l and str(stu['room']) == str(r) and stu.get('status') == 'Active':
            roster.append(stu)
    
    data = []
    for stu in roster:
        sid = str(stu['student_id'])
        g_row = {'test1':0, 'test2':0, 'test3':0, 'final_score':0, 'total_score':0}
        for g in grades_all:
            if (str(g['student_id']) == sid and g['subject'] == s and g['quarter'] == q):
                g_row = g
                break
        data.append({
            'No': stu['class_no'],
            'ID': sid,
            'Name': stu['student_name'],
            'Test 1': g_row['test1'],
            'Test 2': g_row['test2'],
            'Test 3': g_row['test3'],
            'Final': g_row['final_score'],
            'Total': g_row['total_score']
        })
    
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.astype(str)
        df['No'] = pd.to_numeric(df['No'])
        df = df.sort_values('No')
        st.dataframe(df.style.format(precision=1), width=1000)
        st.download_button("⬇️ Excel", df.to_csv(index=False), f"gradebook_{s}_{q}.csv", "text/csv")

def page_student_record_teacher_view():
    st.title("👤 Student Individual Record")
    st.info("Select a student to view their detailed academic summary.")
    
    active_students = get_all_active_students_list()
    
    search_tabs = st.tabs(["🔍 Quick Search", "📂 Filter by Class"])
    s_search = None
    
    with search_tabs[0]:
        if not active_students.empty:
            active_students['label'] = active_students.apply(
                lambda x: f"{x['student_name']} ({x['student_id']}) - {x['grade_level']}/{x['room']}", axis=1
            )
            # FIX: Index=None and Placeholder
            selection = st.selectbox("Find Student", active_students['label'], index=None, placeholder="Type Name or ID to search...", key="quick_search")
            if selection:
                s_search = selection.split('(')[1].split(')')[0]
                
    with search_tabs[1]:
        c1, c2, c3 = st.columns(3)
        f_lvl = c1.selectbox("Level", ["M1","M2","M3","M4","M5","M6"], key="f_lvl")
        f_rm = c2.selectbox("Room", [str(i) for i in range(1,16)], key="f_rm")
        filtered = active_students[
            (active_students['grade_level'] == f_lvl) & 
            (active_students['room'].astype(str) == f_rm)
        ]
        if not filtered.empty:
            s_name_sel = c3.selectbox("Student", filtered['student_name'], key="f_stu")
            if s_name_sel:
                s_row = filtered[filtered['student_name'] == s_name_sel].iloc[0]
                s_search = str(s_row['student_id'])
        else: c3.warning("No students.")

    if s_search:
        details = get_student_details(s_search)
        if details:
            name, lvl, rm, photo, stat = details
            c_info, c_table = st.columns([1, 3])
            with c_info:
                if photo: st.image(Image.open(io.BytesIO(photo)), width=180)
                else: st.image("https://cdn-icons-png.flaticon.com/512/3237/3237472.png", width=180)
                if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0
                with st.popover("📷 Upload Photo"):
                    ukey = st.session_state.uploader_key
                    stu_pic = st.file_uploader("Upload", type=['jpg','png'], key=f"s_rec_up_{s_search}_{ukey}")
                    if stu_pic:
                        update_student_pic(s_search, stu_pic.getvalue())
                        st.toast("✅ Photo Updated!")
                        st.session_state.uploader_key += 1
                        time.sleep(1.0); st.rerun()
                st.markdown(f"### {name}")
                st.caption(f"ID: {s_search}")
                st.info(f"Class: {lvl} / {rm}")
            with c_table:
                df = get_student_grades_for_teacher_view(s_search, st.session_state.user[0])
                if not df.empty: display_academic_transcript(df)
                else: st.warning("No grades recorded by you.")

def display_academic_transcript(df):
    pivot = df.pivot_table(index=['school_year', 'subject'], columns='quarter', values='total_score', aggfunc='first').reset_index()
    for q in ['Q1', 'Q2', 'Q3', 'Q4']:
        if q not in pivot.columns: pivot[q] = 0.0
    pivot['Sem 1'] = pivot['Q1'].fillna(0) + pivot['Q2'].fillna(0)
    pivot['Sem 2'] = pivot['Q3'].fillna(0) + pivot['Q4'].fillna(0)
    pivot['GPA S1'] = pivot['Sem 1'].apply(get_grade_point)
    pivot['GPA S2'] = pivot['Sem 2'].apply(get_grade_point)
    unique_years = pivot['school_year'].unique()
    
    def highlight_low(val):
        try:
            v = float(val)
            if v < 50.0 and v > 4.0: return 'color: red; font-weight: bold;'
            if v < 1.0 and v <= 4.0: return 'color: red; font-weight: bold;'
        except: pass
        return ''

    for yr in unique_years:
        st.markdown(f"#### 🗓️ Academic Year: {yr}")
        yr_data = pivot[pivot['school_year'] == yr].copy()
        display_df = yr_data[['subject', 'Q1', 'Q2', 'Sem 1', 'GPA S1', 'Q3', 'Q4', 'Sem 2', 'GPA S2']].copy()
        display_df.columns = ['Subject', 'Q1 (50)', 'Q2 (50)', 'Sem 1 Total', 'S1 Grade', 'Q3 (50)', 'Q4 (50)', 'Sem 2 Total', 'S2 Grade']
        st.dataframe(display_df.style.format(precision=1).map(highlight_low), hide_index=True, width=1000)
        
        with st.expander("🔎 View Task Details"):
            st.info("Showing raw task scores for these subjects.")
            all_tasks = fetch_all_records("Tasks")
            student_tasks = [t for t in all_tasks if str(t['student_id']) == str(df.iloc[0]['student_id']) and t['school_year'] == yr]
            if student_tasks:
                task_df = pd.DataFrame(student_tasks)
                task_view = task_df[['subject', 'quarter', 'test_name', 't1', 't2', 't3', 't4', 't5', 'raw_total']]
                st.dataframe(task_view, hide_index=True, width=1000)
            else: st.caption("No task details found.")

def page_student_portal_grades():
    s_data = st.session_state.user
    s_id = s_data[0]
    st.title("📜 My Academic Record")
    st.info(f"Welcome, {s_data[1]}.")
    df = get_student_full_report(s_id)
    if not df.empty: display_academic_transcript(df)
    else: st.warning("No grades found.")

def page_student_settings():
    st.title("⚙️ Settings")
    with st.form("pwd_change"):
        p1 = st.text_input("New Password", type="password")
        p2 = st.text_input("Confirm New Password", type="password")
        if st.form_submit_button("Update Password"):
            if p1 == p2 and p1:
                change_student_password(st.session_state.user[0], p1)
                st.success("✅ Password updated! Please log out.")
            else: st.error("⚠️ Passwords do not match.")

# --- MAIN ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    init_db()

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