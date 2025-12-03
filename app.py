import streamlit as st
import pandas as pd
import io
import time
import datetime
import gspread
import json
import os
import socket
import sqlite3
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

# --- CSS STYLING ---
st.markdown("""
<style>
    /* GLOBAL FONTS */
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600&display=swap');
    
    html, body, [class*="css"]  {
        font-family: 'Poppins', sans-serif;
    }
    
    /* METRIC CARDS - Adaptive Theme */
    [data-testid="stMetric"] {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    [data-testid="stMetric"] label {
        color: var(--text-color) !important;
    }
    
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: var(--primary-color) !important;
    }

    /* BUTTONS */
    .stButton > button {
        background: linear-gradient(90deg, #2b5876 0%, #4e4376 100%);
        color: white !important;
        border: none;
        border-radius: 10px;
        font-weight: 600;
        padding: 0.6rem 1.5rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
    }
    .stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 6px 12px rgba(0,0,0,0.3);
        color: #fff !important;
    }

    /* TABLES - Text Size & Visibility */
    div[data-testid="stDataEditor"] * { 
        font-size: 1.15rem !important; 
    }
    div[data-testid="stDataFrame"] * { 
        font-size: 1.15rem !important; 
    }
    
    /* RADIO BUTTONS & INPUTS */
    .stRadio > label { 
        font-size: 1.1rem !important; 
        color: var(--text-color);
    }
    
    /* SLOGAN TEXT */
    .slogan-style {
        font-size: 1.2rem;
        font-weight: 300;
        font-style: italic;
        color: var(--text-color);
        opacity: 0.8;
        margin-bottom: 10px;
        text-align: center;
    }
    
    /* LOGIN HEADER */
    h1 {
        background: -webkit-linear-gradient(#2b5876, #4e4376);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 0px 0px 1px rgba(255,255,255,0.1); 
    }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTS ---
SHEET_NAME = "SGS_Database" 
LOCAL_DB = "sgs_local_db.sqlite"
SCHOOL_CODE = "SK2025"
STUDENT_STATUSES = ["Active", "Transferred", "Dropped Out", "Graduate", "Deleted"]

# --- DATA MANAGER (OPTIMIZED) ---

@st.cache_data(ttl=30, show_spinner=False)
def is_online():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=1.0)
        return True
    except OSError:
        return False

def get_data_mode():
    if is_online(): return 'Cloud'
    return 'Local'

@st.cache_resource
def get_cloud_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp" not in st.secrets: return None
        json_str = st.secrets["gcp"]["service_account_json"]
        creds_dict = json.loads(json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME)
    except Exception as e:
        print(f"Cloud Error: {e}")
        return None

@st.cache_resource
def init_db():
    conn = sqlite3.connect(LOCAL_DB)
    tables = {
        "Users": ["username", "password", "role", "profile_pic"],
        "Subjects": ["id", "teacher_username", "subject_name"],
        "Students": ["student_id", "student_name", "class_no", "grade_level", "room", "photo", "password", "status"],
        "Grades": ["id", "student_id", "subject", "quarter", "school_year", "test1", "test2", "test3", "final_score", "total_score", "recorded_by", "timestamp"],
        "Config": ["uid", "subject", "quarter", "year", "test_name", "task_name", "max_score"]
    }
    task_cols = ["uid", "student_id", "subject", "quarter", "school_year", "test_name"]
    for i in range(1, 11): task_cols.append(f"t{i}") 
    task_cols.append("raw_total")
    tables["Tasks"] = task_cols

    for table_name, columns in tables.items():
        query = f"SELECT count(name) FROM sqlite_master WHERE type='table' AND name='{table_name}'"
        cursor = conn.execute(query)
        if cursor.fetchone()[0] == 0:
            if table_name == "Users":
                df = pd.DataFrame([["admin", "admin123", "Admin", ""]], columns=columns)
            else:
                df = pd.DataFrame(columns=columns)
            df.to_sql(table_name, conn, index=False)
            
    if get_data_mode() == 'Cloud':
        try:
            sh = get_cloud_connection()
            if sh:
                titles = [w.title for w in sh.worksheets()]
                for t in tables.keys():
                    if t not in titles:
                        ws = sh.add_worksheet(t, 100, len(tables[t]))
                        ws.append_row(tables[t])
                        if t == "Users": ws.append_row(["admin", "admin123", "Admin", ""])
        except: pass
    conn.close()

@st.cache_data(ttl=60)
def fetch_all_records(sheet_name):
    mode = get_data_mode()
    if mode == 'Local':
        try:
            conn = sqlite3.connect(LOCAL_DB)
            df = pd.read_sql(f"SELECT * FROM {sheet_name}", conn)
            conn.close()
            
            cols_to_str = ['student_id', 'password', 'username', 'teacher_username', 'ID']
            for col in cols_to_str:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip().str.replace(r'\.0$', '', regex=True).replace('nan', '')
            
            return df.fillna("").to_dict('records')
        except: return []
    elif mode == 'Cloud':
        for attempt in range(3):
            try:
                sh = get_cloud_connection()
                if not sh: return fetch_all_records_local_fallback(sheet_name)
                return sh.worksheet(sheet_name).get_all_records()
            except gspread.exceptions.WorksheetNotFound: 
                init_db(); time.sleep(1); continue
            except gspread.exceptions.APIError: time.sleep(1); continue
            except Exception: return []
    return []

def fetch_all_records_local_fallback(sheet_name):
    try:
        conn = sqlite3.connect(LOCAL_DB)
        df = pd.read_sql(f"SELECT * FROM {sheet_name}", conn)
        conn.close()
        return df.fillna("").to_dict('records')
    except: return []

def perform_login_sync():
    if is_online():
        try:
            sh = get_cloud_connection()
            if not sh: return False
            conn = sqlite3.connect(LOCAL_DB)
            sheets = ["Users", "Subjects", "Students", "Grades", "Tasks", "Config"]
            for s in sheets:
                try:
                    data = sh.worksheet(s).get_all_records()
                    if data:
                        df = pd.DataFrame(data)
                        df.to_sql(s, conn, if_exists='replace', index=False)
                except: pass
            conn.close()
            return True
        except: return False
    return False

def overwrite_sheet_data(sheet_name, data_list_of_dicts):
    try:
        conn = sqlite3.connect(LOCAL_DB)
        df = pd.DataFrame(data_list_of_dicts)
        df.to_sql(sheet_name, conn, if_exists='replace', index=False)
        conn.close()
    except Exception as e:
        print(f"Local Save Error: {e}")

    if get_data_mode() == 'Cloud':
        try:
            sh = get_cloud_connection()
            if sh:
                ws = sh.worksheet(sheet_name)
                if len(data_list_of_dicts) > 0:
                    headers = list(data_list_of_dicts[0].keys())
                    rows = [headers] + [list(d.values()) for d in data_list_of_dicts]
                    ws.clear()
                    ws.append_rows(rows)
                else: ws.clear()
        except:
            st.warning("⚠️ Saved LOCALLY. Cloud update failed (Connection unstable).")
    else:
        st.warning("⚠️ Saved LOCALLY only (Offline Mode).")

def clear_cache():
    st.cache_data.clear()

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

def clean_id(val):
    """Removes .0 from IDs"""
    return str(val).strip().replace('.0', '')

# --- CONFIG & TASKS ---
def get_task_max_score(subject, quarter, year, test_name, task_name):
    configs = fetch_all_records("Config")
    uid = f"{subject}_{quarter}_{year}_{test_name}_{task_name}"
    for c in configs:
        if c.get('uid') == uid: return float(c.get('max_score', 0))
    return 0.0

def save_task_max_score(subject, quarter, year, test_name, task_name, max_val):
    configs = fetch_all_records("Config")
    uid = f"{subject}_{quarter}_{year}_{test_name}_{task_name}"
    configs = [c for c in configs if c.get('uid') != uid]
    configs.append({"uid": uid, "subject": subject, "quarter": quarter, "year": year, "test_name": test_name, "task_name": task_name, "max_score": float(max_val)})
    overwrite_sheet_data("Config", configs)
    clear_cache()

def get_total_max_score_for_test(subject, quarter, year, test_name):
    configs = fetch_all_records("Config")
    total = 0.0
    for c in configs:
        if c['subject'] == subject and c['quarter'] == quarter and c['year'] == year and c['test_name'] == test_name:
            total += float(c.get('max_score', 0))
    return total

def get_enabled_tasks_count(subject, quarter, year, test_name):
    configs = fetch_all_records("Config")
    count = 0
    for i in range(1, 11):
        t_name = f"Task {i}"
        uid = f"{subject}_{quarter}_{year}_{test_name}_{t_name}"
        for c in configs:
            if c.get('uid') == uid: 
                count = i
                break
    return max(1, count) 

def update_specific_task_column(subject, quarter, year, test_name, task_col, df_input, teacher, total_max_score, weight):
    all_tasks = fetch_all_records("Tasks")
    all_grades = fetch_all_records("Grades")
    scores_map = {clean_id(r['ID']): float(r.get(task_col, 0)) for i, r in df_input.iterrows()}
    
    target_tasks = []
    other_tasks = []
    for t in all_tasks:
        if t['subject'] == subject and t['quarter'] == quarter and t['school_year'] == year and t['test_name'] == test_name: target_tasks.append(t)
        else: other_tasks.append(t)
            
    existing_tasks_map = {clean_id(t['student_id']): t for t in target_tasks}
    updated_rows = []
    grade_updates = {}
    
    for sid, score in scores_map.items():
        if sid in existing_tasks_map: row = existing_tasks_map[sid]
        else: 
            row = {"uid": f"{sid}_{subject}_{quarter}_{year}_{test_name}", "student_id": sid, "subject": subject, "quarter": quarter, "school_year": year, "test_name": test_name, "raw_total":0}
            for i in range(1, 11): row[f"t{i}"] = 0
        
        try:
            task_num = int(task_col.replace("Task ", ""))
            db_col = f"t{task_num}"
        except: db_col = "t1"
        
        row[db_col] = score
        
        rt = 0.0
        for i in range(1, 11): rt += float(row.get(f"t{i}", 0))
        row['raw_total'] = rt
        
        updated_rows.append(row)
        
        weighted = 0.0
        if total_max_score > 0:
            weighted = (row['raw_total'] / total_max_score) * weight
            if weighted > weight: weighted = weight
        grade_updates[sid] = weighted
        
    final_tasks = other_tasks + updated_rows
    overwrite_sheet_data("Tasks", final_tasks)
    
    processed_sids = []
    for g in all_grades:
        if g['subject'] == subject and g['quarter'] == quarter and g['school_year'] == year:
            sid = clean_id(g['student_id'])
            if sid in grade_updates:
                new_val = grade_updates[sid]
                if test_name.startswith("Test 1"): g['test1'] = new_val
                elif test_name.startswith("Test 2"): g['test2'] = new_val
                elif test_name.startswith("Test 3"): g['test3'] = new_val
                g['total_score'] = float(g['test1']) + float(g['test2']) + float(g['test3']) + float(g['final_score'])
                g['recorded_by'] = teacher
                g['timestamp'] = str(datetime.datetime.now())
                processed_sids.append(sid)
                
    for sid, score in grade_updates.items():
        if sid not in processed_sids:
            new_row = {"id": int(time.time())+int(sid), "student_id": sid, "subject": subject, "quarter": quarter, "school_year": year, "test1": 0, "test2": 0, "test3": 0, "final_score": 0, "total_score": score, "recorded_by": teacher, "timestamp": str(datetime.datetime.now())}
            if test_name.startswith("Test 1"): new_row['test1'] = score
            elif test_name.startswith("Test 2"): new_row['test2'] = score
            elif test_name.startswith("Test 3"): new_row['test3'] = score
            all_grades.append(new_row)
            
    overwrite_sheet_data("Grades", all_grades)
    clear_cache()
    return True

def save_batch_tasks_and_grades(subject, quarter, year, test_name, task_df, max_score, weight, teacher):
    all_tasks = fetch_all_records("Tasks")
    all_grades = fetch_all_records("Grades")
    all_tasks = [t for t in all_tasks if not (t['subject'] == subject and t['quarter'] == quarter and t['school_year'] == year and t['test_name'] == test_name)]
    grade_updates = {}
    
    for idx, row in task_df.iterrows():
        sid = clean_id(row['ID'])
        raw_total = 0.0
        row_db = {"uid": f"{sid}_{subject}_{quarter}_{year}_{test_name}", "student_id": sid, "subject": subject, "quarter": quarter, "school_year": year, "test_name": test_name}
        
        for i in range(1, 11):
            val = float(row.get(f'Task {i}', 0))
            row_db[f"t{i}"] = val
            raw_total += val
            
        row_db["raw_total"] = raw_total
        
        weighted = 0.0
        if max_score > 0:
            weighted = (raw_total / max_score) * weight
            if weighted > weight: weighted = weight
        grade_updates[sid] = weighted
        all_tasks.append(row_db)
        
    overwrite_sheet_data("Tasks", all_tasks)
    
    processed_sids = []
    for g in all_grades:
        if g['subject'] == subject and g['quarter'] == quarter and g['school_year'] == year:
            sid = clean_id(g['student_id'])
            if sid in grade_updates:
                new_val = grade_updates[sid]
                if test_name.startswith("Test 1"): g['test1'] = new_val
                elif test_name.startswith("Test 2"): g['test2'] = new_val
                elif test_name.startswith("Test 3"): g['test3'] = new_val
                g['total_score'] = float(g['test1']) + float(g['test2']) + float(g['test3']) + float(g['final_score'])
                g['recorded_by'] = teacher
                g['timestamp'] = str(datetime.datetime.now())
                processed_sids.append(sid)
    for sid, score in grade_updates.items():
        if sid not in processed_sids:
            new_row = {"id": int(time.time())+int(sid), "student_id": sid, "subject": subject, "quarter": quarter, "school_year": year, "test1": 0, "test2": 0, "test3": 0, "final_score": 0, "total_score": score, "recorded_by": teacher, "timestamp": str(datetime.datetime.now())}
            if test_name.startswith("Test 1"): new_row['test1'] = score
            elif test_name.startswith("Test 2"): new_row['test2'] = score
            elif test_name.startswith("Test 3"): new_row['test3'] = score
            all_grades.append(new_row)
    overwrite_sheet_data("Grades", all_grades)
    clear_cache()
    return True, "Batch Save Successful"

def save_final_exam_batch(subject, quarter, year, grade_df, max_score, teacher):
    all_grades = fetch_all_records("Grades")
    all_tasks = fetch_all_records("Tasks")
    all_tasks = [t for t in all_tasks if not (t['subject'] == subject and t['quarter'] == quarter and t['school_year'] == year and t['test_name'] == "Final Exam")]
    grade_updates = {}
    for idx, row in grade_df.iterrows():
        sid = clean_id(row['ID'])
        raw = float(row.get('Raw Score', 0))
        weighted = 0.0
        if max_score > 0:
            weighted = (raw / max_score) * 20.0 
            if weighted > 20.0: weighted = 20.0
        grade_updates[sid] = weighted
        
        row_db = {"uid": f"{sid}_{subject}_{quarter}_{year}_Final Exam", "student_id": sid, "subject": subject, "quarter": quarter, "school_year": year, "test_name": "Final Exam", "raw_total": raw}
        for i in range(1, 11): row_db[f"t{i}"] = 0
        all_tasks.append(row_db)
        
    overwrite_sheet_data("Tasks", all_tasks)
    processed_sids = []
    for g in all_grades:
        if g['subject'] == subject and g['quarter'] == quarter and g['school_year'] == year:
            sid = clean_id(g['student_id'])
            if sid in grade_updates:
                g['final_score'] = grade_updates[sid]
                g['total_score'] = float(g['test1']) + float(g['test2']) + float(g['test3']) + float(g['final_score'])
                g['recorded_by'] = teacher
                g['timestamp'] = str(datetime.datetime.now())
                processed_sids.append(sid)
    for sid, score in grade_updates.items():
        if sid not in processed_sids:
            new_row = {"id": int(time.time()) + int(sid), "student_id": sid, "subject": subject, "quarter": quarter, "school_year": year, "test1": 0, "test2": 0, "test3": 0, "final_score": score, "total_score": score, "recorded_by": teacher, "timestamp": str(datetime.datetime.now())}
            all_grades.append(new_row)
    overwrite_sheet_data("Grades", all_grades)
    clear_cache()
    return True

# --- LOGIC ---
def login_staff(username, password):
    records = fetch_all_records("Users")
    for row in records:
        if str(row['username']).lower() == str(username).lower() and str(row['password']) == str(password):
            return (row['username'], row['password'], row['role'], base64_to_image(row['profile_pic']))
    return None

def login_student(student_id, password):
    records = fetch_all_records("Students")
    s_id_in = clean_id(student_id)
    for row in records:
        if clean_id(row['student_id']) == s_id_in:
            if row.get('status', 'Active') == 'Deleted': return None
            db_pass = str(row['password'])
            is_valid = False
            if not db_pass and str(password) == s_id_in: is_valid = True
            elif str(password) == db_pass: is_valid = True
            if is_valid: return (row['student_id'], row['student_name'], row['password'], base64_to_image(row['photo']), row.get('status','Active'))
    return None

def change_student_password(s_id, new_pass):
    records = fetch_all_records("Students")
    for r in records:
        if clean_id(r['student_id']) == clean_id(s_id): r['password'] = new_pass
    overwrite_sheet_data("Students", records)
    clear_cache()

def register_user(username, password, code):
    if code != SCHOOL_CODE: return False, "❌ Invalid School Code!"
    records = fetch_all_records("Users")
    for r in records:
        if r['username'].lower() == username.lower(): return False, "Taken"
    records.append({"username": username, "password": password, "role": "Teacher", "profile_pic": ""})
    overwrite_sheet_data("Users", records)
    clear_cache()
    return True, "Success"

def update_teacher_credentials(old_u, new_u, new_p):
    users = fetch_all_records("Users")
    if old_u.lower() != new_u.lower():
        for u in users:
            if u['username'].lower() == new_u.lower(): return False, "Username Taken"
    for u in users:
        if u['username'] == old_u:
            u['username'] = new_u
            u['password'] = new_p
    subs = fetch_all_records("Subjects")
    grades = fetch_all_records("Grades")
    if old_u != new_u:
        for s in subs:
            if s['teacher_username'] == old_u: s['teacher_username'] = new_u
        for g in grades:
            if g['recorded_by'] == old_u: g['recorded_by'] = new_u
    overwrite_sheet_data("Users", users)
    overwrite_sheet_data("Subjects", subs)
    overwrite_sheet_data("Grades", grades)
    clear_cache()
    return True, "Updated"

# --- READERS ---
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

def get_all_students_admin(include_deleted=False):
    data = fetch_all_records("Students")
    df = pd.DataFrame(data).astype(str)
    if not df.empty and not include_deleted: df = df[df['status'] != 'Deleted']
    return df

def get_student_details(student_id):
    records = fetch_all_records("Students")
    for r in records:
        if clean_id(r['student_id']) == clean_id(student_id): return (r['student_name'], r['grade_level'], r['room'], base64_to_image(r['photo']), r.get('status','Active'))
    return None

def get_next_class_no(level, room):
    records = fetch_all_records("Students")
    max_no = 0
    for r in records:
        if r['grade_level'] == level and str(r['room']) == str(room) and r.get('status') != 'Deleted':
            if int(r['class_no']) > max_no: max_no = int(r['class_no'])
    return max_no + 1

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
    res = [r for r in records if r.get('status') == 'Active']
    return pd.DataFrame(res)

def get_teacher_subjects_full(teacher):
    records = fetch_all_records("Subjects")
    res = []
    for r in records:
        if r['teacher_username'] == teacher: res.append((r['id'], r['subject_name']))
    return res

def get_subject_student_count(subject_name):
    grades = fetch_all_records("Grades")
    return sum(1 for g in grades if g['subject'] == subject_name)

def fetch_task_records(subject, quarter, year, test_name):
    records = fetch_all_records("Tasks")
    res = {}
    for r in records:
        if r['subject'] == subject and r['quarter'] == quarter and r['school_year'] == year and r['test_name'] == test_name:
            res[clean_id(r['student_id'])] = r
    return res

def get_grade_record(student_id, subject, quarter, year):
    records = fetch_all_records("Grades")
    for r in records:
        if (clean_id(r['student_id']) == clean_id(student_id) and r['subject'] == subject and r['quarter'] == quarter and r['school_year'] == year):
            return (r['test1'], r['test2'], r['test3'], r['final_score'], r['total_score'])
    return None

def get_student_grades_for_teacher_view(student_id, teacher_username):
    records = fetch_all_records("Grades")
    data = [r for r in records if clean_id(r['student_id']) == clean_id(student_id) and r['recorded_by'] == teacher_username]
    return pd.DataFrame(data)

def get_student_full_report(student_id):
    records = fetch_all_records("Grades")
    data = [r for r in records if clean_id(r['student_id']) == clean_id(student_id)]
    return pd.DataFrame(data)

# --- WRITERS (ADMIN) ---
def delete_teacher(username):
    users = fetch_all_records("Users")
    subs = fetch_all_records("Subjects")
    users = [u for u in users if u['username'] != username]
    subs = [s for s in subs if s['teacher_username'] != username]
    overwrite_sheet_data("Users", users)
    overwrite_sheet_data("Subjects", subs)
    clear_cache()

def admin_reset_teacher_password(username, new_pass):
    users = fetch_all_records("Users")
    for u in users:
        if u['username'] == username: u['password'] = new_pass
    overwrite_sheet_data("Users", users)
    clear_cache()

def delete_student_admin(s_id):
    studs = fetch_all_records("Students")
    studs = [s for s in studs if clean_id(s['student_id']) != clean_id(s_id)]
    overwrite_sheet_data("Students", studs)
    clear_cache()

def admin_restore_student(s_id):
    studs = fetch_all_records("Students")
    for s in studs:
        if clean_id(s['student_id']) == clean_id(s_id): s['status'] = "Active"
    overwrite_sheet_data("Students", studs)
    clear_cache()
    return True

def admin_reset_student_password(s_id, new_pass):
    studs = fetch_all_records("Students")
    for s in studs:
        if clean_id(s['student_id']) == clean_id(s_id): s['password'] = new_pass
    overwrite_sheet_data("Students", studs)
    clear_cache()

def update_teacher_pic(username, image_bytes):
    users = fetch_all_records("Users")
    for u in users:
        if u['username'] == username: u['profile_pic'] = image_to_base64(image_bytes)
    overwrite_sheet_data("Users", users)
    clear_cache()

def update_student_pic(student_id, image_bytes):
    studs = fetch_all_records("Students")
    for s in studs:
        if clean_id(s['student_id']) == clean_id(student_id): s['photo'] = image_to_base64(image_bytes)
    overwrite_sheet_data("Students", studs)
    clear_cache()

def add_single_student(s_id, name, no, level, room, status="Active"):
    studs = fetch_all_records("Students")
    s_id = clean_id(s_id)
    for s in studs:
        if clean_id(s['student_id']) == s_id:
            return False, f"⚠️ ID Found: {s['student_name']} ({s['grade_level']}/{s['room']} - {s['status']})"
    studs.append({"student_id": s_id, "student_name": name, "class_no": no, "grade_level": level, "room": room, "photo": "", "password": "", "status": status})
    overwrite_sheet_data("Students", studs)
    clear_cache()
    return True, f"Added {name}"

def update_student_details(s_id, new_name, new_no, new_status):
    studs = fetch_all_records("Students")
    for s in studs:
        if clean_id(s['student_id']) == clean_id(s_id):
            s['student_name'] = new_name
            s['class_no'] = new_no
            s['status'] = new_status
    overwrite_sheet_data("Students", studs)
    clear_cache()
    return True, "Updated"

def delete_single_student(s_id):
    studs = fetch_all_records("Students")
    for s in studs:
        if clean_id(s['student_id']) == clean_id(s_id): s['status'] = "Deleted"
    overwrite_sheet_data("Students", studs)
    clear_cache()
    return True, "Moved to Bin"

def soft_delete_class_roster(level, room):
    studs = fetch_all_records("Students")
    c = 0
    for s in studs:
        if s['grade_level'] == level and str(s['room']) == str(room):
            s['status'] = "Deleted"
            c += 1
    overwrite_sheet_data("Students", studs)
    clear_cache()
    return True, f"Deleted {c}"

def promote_students(from_lvl, from_rm, to_lvl, to_rm):
    studs = fetch_all_records("Students")
    c = 0
    for s in studs:
        if s['grade_level'] == from_lvl and str(s['room']) == str(from_rm) and s.get('status') == 'Active':
            s['grade_level'] = to_lvl
            s['room'] = to_rm
            c += 1
    overwrite_sheet_data("Students", studs)
    clear_cache()
    return True, f"Promoted {c}"

def upload_roster(df, level, room):
    studs = fetch_all_records("Students")
    existing_ids = [clean_id(s['student_id']) for s in studs]
    current_max = 0
    for s in studs:
        if s['grade_level'] == level and str(s['room']) == str(room) and s.get('status') != 'Deleted':
             if int(s['class_no']) > current_max: current_max = int(s['class_no'])
    current_number = current_max + 1
    added = 0
    errors = []
    for index, row in df.iterrows():
        s_id = clean_id(row['ID'])
        if s_id in existing_ids: 
            errors.append(f"Skipped {s_id} (Duplicate)")
            continue
        studs.append({"student_id": s_id, "student_name": str(row['Name']), "class_no": current_number, "grade_level": level, "room": room, "photo": "", "password": "", "status": "Active"})
        existing_ids.append(s_id)
        current_number += 1
        added += 1
    overwrite_sheet_data("Students", studs)
    clear_cache()
    return True, f"Uploaded {added}", errors

def add_subject(teacher, subject):
    subs = fetch_all_records("Subjects")
    for r in subs:
        if r['teacher_username'] == teacher and r['subject_name'] == subject: return False, "Duplicate"
    subs.append({"id": int(time.time()), "teacher_username": teacher, "subject_name": subject})
    overwrite_sheet_data("Subjects", subs)
    clear_cache()
    return True, "Added"

def delete_subject(sub_id):
    subs = fetch_all_records("Subjects")
    subs = [s for s in subs if str(s['id']) != str(sub_id)]
    overwrite_sheet_data("Subjects", subs)
    clear_cache()

def update_subject(sub_id, new_name):
    subs = fetch_all_records("Subjects")
    for s in subs:
        if str(s['id']) == str(sub_id): s['subject_name'] = new_name
    overwrite_sheet_data("Subjects", subs)
    clear_cache()
    return True

# --- UI COMPONENTS ---
def login_screen():
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        st.markdown("## SGS Pro Connect")
        st.image("logo/images.jpeg", width=300)
    with c2:
        st.markdown("<div style='height: 50px;'></div>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center;'>🔐 Login Portal</h1>", unsafe_allow_html=True)
        st.markdown("<p class='slogan-style'>Your School, Connected. Anytime, Anywhere.</p>", unsafe_allow_html=True)
        mode = get_data_mode()
        status_color = "var(--success-color)" if mode == "Cloud" else "var(--warning-color)"
        st.markdown(f"<p style='text-align:center;'>Status: <span style='color:{status_color}; font-weight:bold'>{mode}</span></p>", unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["Staff Login", "Student Portal"])
        with tab1:
            with st.form("staff_login"):
                u = st.text_input("Username")
                p = st.text_input("Password", type="password")
                if st.form_submit_button("Login"):
                    user = login_staff(u, p)
                    if user:
                        with st.spinner("Syncing..."): 
                            success = perform_login_sync()
                            if not success and get_data_mode() == 'Cloud':
                                st.error("⚠️ Cloud Sync Failed! Check connection or secrets.")
                        st.session_state.logged_in = True
                        st.session_state.user = user
                        st.session_state.role = user[2]
                        st.success(f"Welcome, {user[0]}!")
                        time.sleep(0.5); st.rerun()
                    else: 
                        st.error("Invalid credentials")
                        if get_data_mode() == 'Local':
                            st.warning("⚠️ System is in LOCAL MODE. New accounts may not be synced yet.")
            with st.expander("Register New Teacher"):
                with st.form("reg_form"):
                    nu = st.text_input("New Username")
                    np = st.text_input("New Password", type="password")
                    sc = st.text_input("School Code", type="password")
                    if st.form_submit_button("Register"):
                        ok, msg = register_user(nu, np, sc)
                        if ok: st.success("Registered! Login now.")
                        else: st.error(msg)
        with tab2:
            with st.form("student_login"):
                sid = st.text_input("Student ID")
                sp = st.text_input("Password", type="password")
                if st.form_submit_button("Access Portal"):
                    s_user = login_student(sid, sp)
                    if s_user:
                        with st.spinner("Syncing..."): perform_login_sync()
                        st.session_state.logged_in = True
                        st.session_state.user = s_user
                        st.session_state.role = "Student"
                        st.success(f"Welcome, {s_user[1]}")
                        time.sleep(0.5); st.rerun()
                    else: st.error("Invalid ID or Password")

def sidebar_menu():
    if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0
    with st.sidebar:
        role = st.session_state.get('role', 'Teacher')
        user_data = st.session_state.user
        
        if role == "Admin":
            st.markdown(f"### 🛡️ Admin")
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
            menu = st.radio("Menu", ["Dashboard", "📂 Student Roster", "📝 Input Grades", "📊 Gradebook", "👤 Student Record", "⚙️ Account Settings"])
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

def page_dashboard():
    st.title("📊 Dashboard")
    user = st.session_state.user[0]
    
    # --- 1. FETCH DATA ---
    subs = get_teacher_subjects_full(user)
    all_users = fetch_all_records("Users")
    teacher_count = sum(1 for u in all_users if u.get('role') == 'Teacher')
    all_active_students = get_all_active_students_list()
    total_system_students = len(all_active_students)
    
    subject_details = []
    my_total_students = 0
    for s_id, s_name in subs:
        cnt = get_subject_student_count(s_name)
        my_total_students += cnt
        subject_details.append((s_id, s_name, cnt))
        
    # --- 2. METRICS ROW ---
    c1, c2, c3 = st.columns(3)
    c1.metric("My Subjects", len(subs), help=f"You teach {my_total_students} students total")
    c2.metric("Total Active Students", total_system_students, delta="School Wide", delta_color="off")
    c3.metric("Total Teachers", teacher_count, delta="School Wide", delta_color="off")
    
    # --- 3. SUBJECT CARDS ---
    st.markdown("### 📚 My Subjects")
    st.markdown("---")
    
    if not subject_details:
        st.info("You haven't added any subjects yet.")
    
    for s_id, s_name, cnt in subject_details:
        label = f"📘 {s_name} ({cnt} Students)"
        with st.expander(label):
            st.caption(f"Manage settings for {s_name}")
            c_a, c_b = st.columns([3, 1])
            new_name = c_a.text_input("Rename Subject", value=s_name, key=f"ren_{s_id}")
            if c_b.button("Update", key=f"btn_ren_{s_id}"):
                update_subject(s_id, new_name)
                st.success("Renamed!")
                time.sleep(1)
                st.rerun()
            
            st.markdown("---")
            if st.button("🗑️ Delete Subject", key=f"btn_del_{s_id}", help="This will remove the subject from your list."):
                delete_subject(s_id)
                st.warning("Deleted!")
                time.sleep(1)
                st.rerun()

    # --- 4. ADD NEW SUBJECT FORM ---
    st.markdown("### ➕ Add New Subject")
    with st.form("add_sub"):
        c_add1, c_add2 = st.columns([3, 1])
        new_s = c_add1.text_input("Subject Name", placeholder="e.g. Mathematics M1")
        if c_add2.form_submit_button("Add Subject"):
            if new_s:
                ok, msg = add_subject(user, new_s)
                if ok: 
                    st.success(msg)
                    time.sleep(1)
                    st.rerun()
                else: 
                    st.error(msg)

def page_admin_dashboard():
    st.title("🛡️ Admin Dashboard")
    u, a, d, t, b, subs = get_admin_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Users", u)
    c2.metric("Active Students", a)
    c3.metric("Subjects", subs)
    c4.metric("Dropped/Transferred", d+t)

def page_admin_manage_teachers():
    st.title("👥 Manage Teachers")
    teachers = get_all_teachers_with_counts()
    if not teachers.empty: st.dataframe(teachers, width=1000, hide_index=True)
    else: st.info("No teachers found.")
    
    t1, t2, t3 = st.tabs(["Reset Password", "Delete Teacher", "Update Photo"])
    
    with t1:
        with st.form("reset_t_pass"):
            t_user = st.text_input("Username to Reset")
            t_pass = st.text_input("New Password")
            if st.form_submit_button("Reset Password"):
                admin_reset_teacher_password(t_user, t_pass)
                st.success(f"Password for {t_user} reset.")
    
    with t2:
        st.markdown("### 🗑️ Delete Teacher")
        del_t = st.text_input("Enter Username to DELETE")
        if st.button("Delete Teacher"):
            delete_teacher(del_t); st.warning(f"Teacher {del_t} deleted."); time.sleep(1); st.rerun()
            
    with t3:
        st.markdown("### 📷 Update Teacher Photo")
        if not teachers.empty:
            target_t = st.selectbox("Select Teacher", teachers['username'].unique())
            up_t = st.file_uploader("Upload New Photo", type=['jpg','png'], key="adm_t_up")
            if up_t and st.button("Save Photo"):
                update_teacher_pic(target_t, up_t.getvalue())
                st.success(f"Photo for {target_t} updated!")

def page_admin_manage_students():
    st.title("🎓 Manage Students (Admin)")
    tab_list, tab_edit, tab_restore = st.tabs(["📋 Master List", "✏️ Edit / Delete", "♻️ Restore"])
    with tab_list:
        df = get_all_students_admin()
        search = st.text_input("🔍 Search Student", key="adm_search")
        if search: df = df[df['student_name'].str.contains(search, case=False) | df['student_id'].astype(str).str.contains(search)]
        st.dataframe(df, width=1000, hide_index=True)
    with tab_edit:
        st.markdown("### ✏️ Edit Student Account")
        c1, c2, c3 = st.columns([1,2,1])
        target_id = c1.text_input("Enter ID to Edit")
        if target_id:
            with c2.form("admin_stu_edit"):
                new_pass = st.text_input("Set New Password")
                if st.form_submit_button("Reset Password"):
                    admin_reset_student_password(target_id, new_pass)
                    st.success(f"Password for {target_id} reset.")
            
            with c2.expander("📷 Update Student Photo"):
                up_s = st.file_uploader("New Photo", type=['jpg','png'], key="adm_s_up")
                if up_s and st.button("Save Student Photo"):
                    update_student_pic(target_id, up_s.getvalue())
                    st.success("Photo Updated!")
            
            if c3.button("🗑️ Hard Delete", key="del_stu_adm"):
                delete_student_admin(target_id)
                st.warning(f"Student {target_id} permanently deleted."); time.sleep(1); st.rerun()
    with tab_restore:
        st.markdown("### 🗑️ Recycle Bin")
        df_del = get_all_students_admin(include_deleted=True)
        if not df_del.empty: df_del = df_del[df_del['status'] == 'Deleted']
        if not df_del.empty:
            st.dataframe(df_del, width=1000, hide_index=True)
            res_id = st.selectbox("Select Student to Restore", df_del['student_id'].astype(str) + " - " + df_del['student_name'])
            if st.button("♻️ Restore Selected"):
                sid_only = res_id.split(" - ")[0]
                admin_restore_student(sid_only); st.success(f"Student {sid_only} restored!"); time.sleep(1.5); st.rerun()
        else: st.info("Bin is empty.")

def page_roster():
    st.title("📂 Student Roster Management")
    c1, c2 = st.columns(2)
    with c1: level = st.selectbox("Level", ["M1","M2","M3","M4","M5","M6"])
    with c2: room = st.selectbox("Room", [str(i) for i in range(1,16)])
    st.markdown("---")
    t1, t2, t3, t4, t5, t6 = st.tabs(["📤 Bulk Upload", "➕ Manual Add", "✏️ Edit / Status", "🚀 Promote / Transfer", "🗑️ Reset Class", "🔍 Search All Students"])
    
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
                    if errs: st.error(f"{len(errs)} Errors: " + ", ".join(errs[:5]) + "...")
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
            edit_target = st.selectbox("Select Student to Edit", roster['student_id'] + " - " + roster['student_name'])
            if edit_target:
                s_id = edit_target.split(" - ")[0]
                curr_data = roster[roster['student_id'] == s_id].iloc[0]
                with st.form("edit_stu_details"):
                    e_name = st.text_input("Name", value=curr_data['student_name'])
                    e_no = st.number_input("Class No", value=int(curr_data['class_no']))
                    e_stat = st.selectbox("Status", STUDENT_STATUSES, index=STUDENT_STATUSES.index(curr_data['status']))
                    if st.form_submit_button("💾 Save Changes"):
                        ok, msg = update_student_details(s_id, e_name, int(e_no), e_stat)
                        if ok: st.success(msg); time.sleep(1); st.rerun()
            st.divider()
            st.markdown("### Quick Status Update")
            for idx, row in roster.iterrows():
                c_x, c_y = st.columns([3, 1])
                c_x.text(f"{row['class_no']}. {row['student_name']} ({row['status']})")
                if c_y.button("🗑️ Bin", key=f"bin_{row['student_id']}_{idx}"): 
                    delete_single_student(row['student_id']); st.rerun()
        else: st.info("Class is empty.")
    with t4:
        st.markdown("### 🚀 Batch Promote / Transfer")
        c_p1, c_p2 = st.columns(2)
        to_lvl = c_p1.selectbox("To Level", ["M1","M2","M3","M4","M5","M6"], key="to_lvl")
        to_rm = c_p2.selectbox("To Room", [str(i) for i in range(1,16)], key="to_rm")
        if st.button(f"Move ALL Active Students from {level}/{room} to {to_lvl}/{to_rm}"):
            ok, msg = promote_students(level, room, to_lvl, to_rm)
            if ok: st.success(msg); time.sleep(1.5); st.rerun()
    with t5:
        st.markdown("### ⚠️ Danger Zone")
        if st.button("🗑️ Delete ALL Students in this Class"):
            ok, msg = soft_delete_class_roster(level, room)
            if ok: st.warning(msg); time.sleep(1.5); st.rerun()
            
    with t6:
        st.markdown("### 🔍 Global Student Search")
        search_term = st.text_input("Enter Student Name or ID", placeholder="Search whole school...")
        if search_term:
            all_studs = get_all_students_admin(include_deleted=True)
            results = all_studs[all_studs['student_name'].str.contains(search_term, case=False) | all_studs['student_id'].astype(str).str.contains(search_term)]
            if not results.empty:
                st.dataframe(results[['student_id', 'student_name', 'grade_level', 'room', 'status']], hide_index=True)
            else:
                st.info("No students found.")

    st.markdown("---")
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

    c_zoom, c_pad = st.columns([1, 4])
    with c_zoom: zoom = st.slider("🔍 Zoom Table", 80, 150, 100, 10)
    st.markdown(f"""<style>div[data-testid="stDataFrame"] {{ zoom: {zoom}%; }}</style>""", unsafe_allow_html=True)
    
    if "active_test_tab" not in st.session_state: st.session_state.active_test_tab = "Test 1"
    test_options = ["Test 1", "Test 2", "Test 3", "Final Exam", "Bulk Upload"]
    try: idx = test_options.index(st.session_state.active_test_tab)
    except: idx = 0
    selected_tab = st.radio("Select Input Mode", test_options, index=idx, horizontal=True)
    st.session_state.active_test_tab = selected_tab
    st.markdown("---")

    if selected_tab in ["Test 1", "Test 2", "Test 3"]:
        test_name = selected_tab
        weight = 10.0
        
        # --- STATUS BAR LOGIC ---
        total_test_max = get_total_max_score_for_test(subj, q, yr, test_name)
        existing_tasks = fetch_task_records(subj, q, yr, test_name)
        pass_count = 0
        fail_count = 0
        
        if total_test_max > 0:
            for index, row in roster.iterrows():
                sid = str(row['student_id'])
                t_rec = existing_tasks.get(sid, {})
                raw_total = float(t_rec.get('raw_total', 0))
                if raw_total >= (total_test_max / 2): pass_count += 1
                else: fail_count += 1
        
        # STATUS BAR DISPLAY
        st.markdown(f"### 📊 Class Performance: {test_name} ({int(weight)}pts)")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Students", len(roster))
        m2.metric("Passing", pass_count, delta="Good", delta_color="normal")
        m3.metric("Failing", fail_count, delta="-Needs Imprv", delta_color="inverse")
        m4.metric("Test Max Score", int(total_test_max))
        st.markdown("---")

        st.markdown(f"### {test_name} Input")
        
        # --- DYNAMIC TASK SELECTOR ---
        active_count = get_enabled_tasks_count(subj, q, yr, test_name)
        
        col_sel, col_add = st.columns([4, 1])
        with col_add:
            if st.button("➕ Add Task"):
                if active_count < 10:
                    # Activate next task by setting dummy config
                    next_t = active_count + 1
                    save_task_max_score(subj, q, yr, test_name, f"Task {next_t}", 0)
                    st.rerun()
        
        with col_sel:
            options = [f"Task {i}" for i in range(1, active_count + 1)]
            options.append("All Tasks (Overview)")
            task_choice = st.radio("Select Task to Grade", options, horizontal=True)
        
        if task_choice == "All Tasks (Overview)":
            st.info("ℹ️ Overview Mode: View all enabled tasks and Weighted Score.")
            # Calculate total max score
            total_test_max = get_total_max_score_for_test(subj, q, yr, test_name)
            
            # Fetch data
            existing_tasks = fetch_task_records(subj, q, yr, test_name)
            editor_data = []
            
            for index, row in roster.iterrows():
                sid = str(row['student_id'])
                t_rec = existing_tasks.get(sid, {})
                
                raw_sum = 0.0
                row_data = {
                    "No": row['class_no'], 
                    "ID": sid, 
                    "Name": row['student_name']
                }
                
                # Add columns for active tasks
                for i in range(1, active_count + 1):
                    val = float(t_rec.get(f't{i}', 0))
                    row_data[f"Task {i}"] = val
                    raw_sum += val
                
                row_data["Total Raw"] = raw_sum
                
                # Calc Weighted
                w_score = 0.0
                if total_test_max > 0:
                    w_score = (raw_sum / total_test_max) * weight
                    if w_score > weight: w_score = weight
                row_data["Weighted Score"] = w_score
                
                # Status
                status = "Pass"
                if total_test_max > 0 and raw_sum < (total_test_max/2): status = "Fail"
                row_data["Status"] = status
                
                editor_data.append(row_data)
            
            df_editor = pd.DataFrame(editor_data)
            
            # Dynamic Column Config
            col_config = {
                "No": st.column_config.NumberColumn(disabled=True, width="small"),
                "ID": st.column_config.TextColumn(disabled=True),
                "Name": st.column_config.TextColumn(disabled=True),
                "Total Raw": st.column_config.NumberColumn(disabled=True),
                "Weighted Score": st.column_config.NumberColumn(disabled=True, format="%.2f"),
                "Status": st.column_config.TextColumn(disabled=True)
            }
            
            with st.form(key=f"form_{test_name}_all"):
                edited_df = st.data_editor(df_editor, hide_index=True, column_config=col_config, width=1200, height=500, key=f"ed_{test_name}_all")
                if st.form_submit_button("💾 Save All Tasks"):
                    with st.spinner("Saving batch..."):
                        ok, msg = save_batch_tasks_and_grades(subj, q, yr, test_name, edited_df, total_test_max, weight, st.session_state.user[0])
                        if ok: st.success(msg); time.sleep(0.5); st.rerun()

        else:
            # --- INDIVIDUAL TASK MODE ---
            current_max = get_task_max_score(subj, q, yr, test_name, task_choice)
            new_max = st.number_input(f"Maximum Score for {task_choice}", min_value=0.0, value=current_max, step=1.0)
            
            # SAVE MAX SCORE IF CHANGED
            if new_max != current_max:
                save_task_max_score(subj, q, yr, test_name, task_choice, new_max)
                st.rerun()

            # DISABLE/HIDE IF MAX SCORE IS 0
            if new_max <= 0:
                st.warning(f"⚠️ Please set the **Maximum Score** for {task_choice} above 0 to enable grading.")
            else:
                editor_data = []
                # Map Task Choice to DB key (Task 1 -> t1)
                t_num = int(task_choice.split(" ")[1])
                task_key = f"t{t_num}"
                
                for index, row in roster.iterrows():
                    sid = str(row['student_id'])
                    t_rec = existing_tasks.get(sid, {})
                    current_score = float(t_rec.get(task_key, 0))
                    raw_total = float(t_rec.get('raw_total', 0)) 
                    
                    # Calc Weighted
                    w_score = 0.0
                    if total_test_max > 0:
                        w_score = (raw_total / total_test_max) * weight
                        if w_score > weight: w_score = weight
                    
                    row_data = {
                        "No": row['class_no'], 
                        "ID": sid, 
                        "Name": row['student_name'],
                        task_choice: current_score,
                        "Weighted Score": w_score
                    }
                    editor_data.append(row_data)
                
                df_editor = pd.DataFrame(editor_data)
                col_config = {
                    "No": st.column_config.NumberColumn(disabled=True, width="small"),
                    "ID": st.column_config.TextColumn(disabled=True),
                    "Name": st.column_config.TextColumn(disabled=True),
                    task_choice: st.column_config.NumberColumn(min_value=0, max_value=int(new_max)),
                    "Weighted Score": st.column_config.NumberColumn(disabled=True, format="%.2f")
                }
                
                with st.form(key=f"form_{test_name}_{task_choice}"):
                    edited_df = st.data_editor(df_editor, hide_index=True, column_config=col_config, width=1200, height=500, key=f"ed_{test_name}_{task_choice}")
                    if st.form_submit_button(f"💾 Save {task_choice}"):
                        with st.spinner("Saving..."):
                            ok = update_specific_task_column(subj, q, yr, test_name, task_choice, edited_df, st.session_state.user[0], total_test_max, weight)
                            if ok: st.success("Saved!"); time.sleep(0.5); st.rerun()

    elif "Final" in selected_tab:
        st.markdown("### 🏁 Final Exam Input")
        max_final = st.number_input("Perfect Score for Final Exam", min_value=1.0, value=50.0)
        existing_tasks = fetch_task_records(subj, q, yr, "Final Exam")
        pass_count = 0
        fail_count = 0
        final_data = []
        for index, row in roster.iterrows():
            sid = str(row['student_id'])
            raw_val = float(existing_tasks.get(sid, {}).get('raw_total', 0))
            w_val = 0.0
            if max_final > 0:
                w_val = (raw_val / max_final) * 20.0
                if w_val > 20.0: w_val = 20.0
            if raw_val >= (max_final / 2): pass_count += 1
            else: fail_count += 1
            final_data.append({"No": row['class_no'], "ID": sid, "Name": row['student_name'], "Raw Score": raw_val, "Weighted (20%)": w_val})
        
        st.markdown(f"### 📊 Class Performance: Final Exam (20pts)")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Students", len(roster))
        m2.metric("Passing", pass_count, delta="Good", delta_color="normal")
        m3.metric("Failing", fail_count, delta="-Needs Imprv", delta_color="inverse")
        m4.metric("Exam Max", int(max_final))
        st.markdown("---")

        df_final = pd.DataFrame(final_data)
        with st.form("final_form"):
            edited_final = st.data_editor(df_final, hide_index=True, column_config={
                    "No": st.column_config.NumberColumn(disabled=True, width="small"),
                    "ID": st.column_config.TextColumn(disabled=True),
                    "Name": st.column_config.TextColumn(disabled=True),
                    "Weighted (20%)": st.column_config.NumberColumn(disabled=True, format="%.2f")
                }, width=1000, height=500)
            if st.form_submit_button("💾 Save Final Scores"):
                 with st.spinner("Saving..."):
                    ok = save_final_exam_batch(subj, q, yr, edited_final, max_final, st.session_state.user[0])
                    if ok: st.success("Saved!"); time.sleep(0.5); st.rerun()

    elif selected_tab == "Bulk Upload":
        st.markdown("### 📤 Bulk Upload Grades")
        target_test = st.selectbox("Select Target", ["Test 1", "Test 2", "Test 3", "Final Exam"])
        weight = 20.0 if target_test == "Final Exam" else 10.0
        
        # User defines max score for the whole upload
        upload_max_score = st.number_input(f"Total Max Raw Score for {target_test} (Sum of all tasks)", min_value=1.0, value=50.0)
        
        st.info("ℹ️ Upload overwrites existing scores for this test. Columns Task 1...Task 10 are supported.")
        
        if st.button("⬇️ Download Template"):
            tmp = roster[['class_no', 'student_id', 'student_name']].copy()
            tmp = tmp.rename(columns={'student_id': 'ID', 'student_name': 'Name'})
            for i in range(1, 11): tmp[f'Task {i}'] = 0
            
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                tmp.to_excel(writer, index=False)
            st.download_button("Download .xlsx", out.getvalue(), "template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            
        up_file = st.file_uploader("Upload Excel", type=['xlsx'])
        if up_file:
            if st.button("Process Upload"):
                try:
                    df = pd.read_excel(up_file)
                    # Normalize columns if needed
                    if "Student ID" in df.columns: df = df.rename(columns={"Student ID": "ID"})
                    
                    ok, msg = save_batch_tasks_and_grades(subj, q, yr, target_test, df, upload_max_score, weight, st.session_state.user[0])
                    if ok: st.success(msg); time.sleep(1.5); st.rerun()
                    else: st.error(msg)
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
    roster = get_class_roster(l, r, only_active=True)
    if roster.empty: st.info("No students."); return
    data = []
    yr = get_school_years()[0] 
    for idx, row in roster.iterrows():
        sid = str(row['student_id'])
        rec = get_grade_record(sid, s, q, yr)
        if rec:
            t1, t2, t3, fin, tot = rec
            gp = get_grade_point(float(tot))
            data.append({"No": row['class_no'], "Name": row['student_name'], "Test 1": fmt_score(float(t1)), "Test 2": fmt_score(float(t2)), "Test 3": fmt_score(float(t3)), "Final": fmt_score(float(fin)), "Total": fmt_score(float(tot)), "GPA": gp})
        else:
             data.append({"No": row['class_no'], "Name": row['student_name'], "Test 1": "-", "Test 2": "-", "Test 3": "-", "Final": "-", "Total": "-", "GPA": "-"})
    st.dataframe(pd.DataFrame(data), hide_index=True, width=1200)
    
    # --- DOWNLOAD BUTTON ---
    if data:
        # Create a new DataFrame for export with specific columns
        export_data = []
        for row in data:
            export_data.append({
                "No.": row["No"],
                "Name": row["Name"],
                "Test 1(10)": row["Test 1"],
                "Test 2(10)": row["Test 2"],
                "Test 3(10)": row["Test 3"],
                "Final(20)": row["Final"]
            })
        
        df_export = pd.DataFrame(export_data)
        
        # Create Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, index=False, sheet_name="Gradebook")
            
        st.download_button(
            label="⬇️ Download Gradebook (Excel)",
            data=buffer.getvalue(),
            file_name=f"Gradebook_{s}_{l}_{r}_{q}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

def page_student_record_teacher_view():
    st.title("👤 Student Individual Record")
    active_students = get_all_active_students_list()
    search_tabs = st.tabs(["🔍 Quick Search", "📂 Filter by Class"])
    s_search = None
    with search_tabs[0]:
        if not active_students.empty:
            active_students['label'] = active_students.apply(lambda x: f"{x['student_name']} ({x['student_id']}) - {x['grade_level']}/{x['room']}", axis=1)
            selection = st.selectbox("Find Student", active_students['label'], index=None, placeholder="Type Name or ID...", key="quick_search")
            if selection: s_search = selection.split('(')[1].split(')')[0]
    with search_tabs[1]:
        c1, c2, c3 = st.columns(3)
        f_lvl = c1.selectbox("Level", ["M1","M2","M3","M4","M5","M6"], key="f_lvl")
        f_rm = c2.selectbox("Room", [str(i) for i in range(1,16)], key="f_rm")
        filtered = active_students[(active_students['grade_level'] == f_lvl) & (active_students['room'].astype(str) == f_rm)]
        if not filtered.empty:
            s_name_sel = c3.selectbox("Student", filtered['student_name'], key="f_stu")
            if s_name_sel: s_search = str(filtered[filtered['student_name'] == s_name_sel].iloc[0]['student_id'])
    if s_search:
        details = get_student_details(s_search)
        if details:
            name, lvl, rm, photo, stat = details
            c_info, c_table = st.columns([1, 3])
            with c_info:
                if photo: st.image(Image.open(io.BytesIO(photo)), width=150)
                else: st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=150)
                st.markdown(f"**{name}**\nID: {s_search} | {lvl}/{rm}\nStatus: {stat}")
                with st.expander("📷 Update Photo"):
                    up = st.file_uploader("Upload New Photo", type=['jpg','png'], key=f"u_stu_{s_search}")
                    if up and st.button("Save Photo", key=f"b_stu_{s_search}"):
                        update_student_pic(s_search, up.getvalue())
                        st.success("Photo Updated!"); time.sleep(1); st.rerun()
            with c_table:
                st.markdown("### 📜 Academic History")
                report = get_student_full_report(s_search)
                if not report.empty:
                    disp = report[['school_year', 'quarter', 'subject', 'total_score', 'final_score']]
                    disp['GPA'] = disp['total_score'].apply(lambda x: get_grade_point(float(x)))
                    st.dataframe(disp, hide_index=True)
                else: st.info("No grades recorded.")

def page_teacher_settings():
    st.title("⚙️ Account Settings")
    current_u = st.session_state.user[0]
    current_p = st.session_state.user[1]
    c_set1, c_set2 = st.columns(2)
    with c_set1:
        with st.form("teach_settings"):
            st.markdown("### 🔐 Credentials")
            new_u = st.text_input("Username", value=current_u)
            new_p = st.text_input("Password", value=current_p, type="password")
            if st.form_submit_button("💾 Update Credentials"):
                if new_u and new_p:
                    with st.spinner("Updating..."):
                        ok, msg = update_teacher_credentials(current_u, new_u, new_p)
                        if ok: st.success(msg); st.session_state.logged_in = False; time.sleep(2); st.rerun()
                        else: st.error(msg)
                else: st.warning("Fields cannot be empty.")
    with c_set2:
        st.markdown("### 📷 Profile Picture")
        up_t = st.file_uploader("Upload New Photo", type=['jpg','png'], key="sett_t_up")
        if up_t and st.button("Save Profile Photo"):
            update_teacher_pic(current_u, up_t.getvalue())
            st.success("Photo Updated! Please log out to see changes in sidebar.")

def page_student_portal_grades():
    s_data = st.session_state.user
    s_id = s_data[0]
    st.title("📜 My Academic Record")
    st.info(f"Viewing grades for {s_data[1]}")
    df = get_student_full_report(s_id)
    if not df.empty:
        df['GPA'] = df['total_score'].apply(lambda x: get_grade_point(float(x)))
        st.dataframe(df[['school_year','quarter','subject','test1','test2','test3','final_score','total_score','GPA']], hide_index=True)
    else: st.info("No grades available yet.")
    st.markdown("### 📊 Task Details")
    yr = get_school_years()[0] 
    all_tasks = fetch_all_records("Tasks")
    student_tasks = [t for t in all_tasks if str(t['student_id']) == str(s_id) and t['school_year'] == yr]
    if student_tasks:
        st.dataframe(pd.DataFrame(student_tasks)[['subject', 'quarter', 'test_name', 't1', 't2', 't3', 't4', 't5', 'raw_total']], hide_index=True, width=1000)
    else: st.caption("No task details found.")

def page_student_settings():
    st.title("⚙️ My Settings")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 📷 Update Photo")
        up = st.file_uploader("Upload New Profile Picture", type=['jpg','png'])
        if up:
            if st.button("Save Photo"):
                update_student_pic(st.session_state.user[0], up.getvalue())
                st.success("Photo updated! Please log out.")
    with c2:
        st.markdown("### 🔐 Change Password")
        with st.form("student_pass_change"):
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
        elif sel == "⚙️ Account Settings": page_teacher_settings()
    else:
        if sel == "📜 My Grades": page_student_portal_grades()
        elif sel == "⚙️ Settings": page_student_settings()