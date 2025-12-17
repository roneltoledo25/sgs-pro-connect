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
import altair as alt
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
import base64

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="SGS Pro Connect",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- MODERN UI & CSS STYLING ---
def load_custom_css():
    st.markdown("""
    <style>
        /* IMPORT FONT */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
        
        html, body, [class*="css"]  {
            font-family: 'Inter', sans-serif;
        }

        /* PRIMARY GRADIENT BACKGROUND FOR HEADERS */
        .stAppHeader {
            background-color: transparent;
        }

        /* METRIC CARDS - Modern Card Style */
        div[data-testid="stMetric"] {
            background-color: #ffffff;
            border: 1px solid #e0e0e0;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            transition: transform 0.2s;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 15px rgba(0,0,0,0.1);
        }
        
        [data-testid="stMetricLabel"] {
            color: #555;
            font-size: 0.9rem;
            font-weight: 600;
        }
        
        [data-testid="stMetricValue"] {
            color: #2b5876;
            font-weight: 700;
        }

        /* CUSTOM BUTTONS */
        .stButton > button {
            background: linear-gradient(135deg, #2b5876 0%, #4e4376 100%);
            color: white !important;
            border: none;
            border-radius: 8px;
            padding: 0.5rem 1.2rem;
            font-weight: 600;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.2);
            opacity: 0.95;
        }

        /* LOGIN SCREEN HEADER */
        .login-header {
            background: -webkit-linear-gradient(#2b5876, #4e4376);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
            font-size: 2.5rem;
            margin-bottom: 0px;
        }
        .slogan-style {
            font-size: 1.1rem;
            color: #666;
            font-style: italic;
            margin-bottom: 2rem;
        }

        /* TAB STYLING */
        .stTabs [data-baseweb="tab-list"] {
            gap: 20px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            border-radius: 8px;
            padding: 0px 20px;
            background-color: #f0f2f6;
            border: none;
            font-weight: 600;
        }
        .stTabs [aria-selected="true"] {
            background-color: #e3f2fd;
            color: #1976d2;
        }

        /* DATAFRAME & EDITOR POLISH */
        [data-testid="stDataFrame"] {
            border: 1px solid #eee;
            border-radius: 10px;
            overflow: hidden;
        }
    </style>
    """, unsafe_allow_html=True)

load_custom_css()

# --- CONSTANTS ---
SHEET_NAME = "SGS_Database" 
LOCAL_DB = "sgs_local_db.sqlite"
SCHOOL_CODE = "SK2025"
STUDENT_STATUSES = ["Active", "Transferred", "Dropped Out", "Graduate", "Deleted"]

# --- DATA MANAGER ---

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
        "Config": ["uid", "subject", "quarter", "year", "test_name", "task_name", "max_score"],
        "Attendance": ["uid", "student_id", "student_name", "subject", "date", "status", "recorded_by", "timestamp"]
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
            st.toast("⚠️ Saved LOCALLY. Cloud update failed (Connection unstable).", icon="📂")
    else:
        st.toast("⚠️ Saved LOCALLY only (Offline Mode).", icon="📂")

def clear_cache():
    st.cache_data.clear()

# --- HELPER FUNCTIONS ---
def get_school_years():
    """
    Calculates the school years based on a May-to-April cycle.
    Returns: A list of 3 school years: [Previous, Current, Next]
    """
    now = datetime.datetime.now()
    current_year = now.year
    current_month = now.month
    
    # Determine the start year of the CURRENT school year (May-April cycle)
    # School year runs from May of 'start_year' to April of 'start_year + 1'
    if current_month >= 5: # May (5) to December (12)
        start_year = current_year
    else: # January (1) to April (4)
        start_year = current_year - 1
        
    current_sy = f"{start_year}-{start_year + 1}"
    prev_sy = f"{start_year - 1}-{start_year}"
    next_sy = f"{start_year + 1}-{start_year + 2}"
    
    # Return previous, current, next
    return [prev_sy, current_sy, next_sy]

def fmt_score(val):
    if val % 1 == 0: return f"{int(val)}"
    return f"{val:.1f}"

def get_sem_gpa(score):
    """
    Custom Grading Scale:
    80-100 = 4.0 | 75-79 = 3.5 | 70-74 = 3.0 | 65-69 = 2.5
    60-64  = 2.0 | 55-59 = 1.5 | 50-54 = 1.0 | 0-49  = 0.0
    """
    if score >= 80: return 4.0
    elif score >= 75: return 3.5
    elif score >= 70: return 3.0
    elif score >= 65: return 2.5
    elif score >= 60: return 2.0
    elif score >= 55: return 1.5
    elif score >= 50: return 1.0
    else: return 0.0

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
        img.thumbnail((200, 200)) # Slightly larger for better quality
        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=80)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except: return ""

def base64_to_image(b64_str):
    if not b64_str: return None
    try: return base64.b64decode(b64_str)
    except: return None

def clean_id(val):
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

def get_attendance_score_data(subject_name):
    # 1. Fetch data using the app's hybrid (Cloud/Local) loader
    all_records = fetch_all_records("Attendance")
    
    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    
    # 2. Filter for the specific subject
    # Ensure column names match your DB schema
    if 'subject' not in df.columns: return pd.DataFrame()
    
    df = df[df['subject'] == subject_name]
    
    if df.empty:
        return pd.DataFrame()

    # 3. Calculate Logic
    # Group by Student ID and count statuses
    summary = df.groupby('student_id')['status'].value_counts().unstack(fill_value=0)
    
    # Ensure columns exist
    for col in ['Present', 'Late', 'Absent', 'Excused']:
        if col not in summary.columns:
            summary[col] = 0

    # 4. Math for the Score (Max 5 points)
    summary['Total_Classes'] = summary['Present'] + summary['Late'] + summary['Absent'] + summary['Excused']
    
    # Weighted attendance: Present = 1, Late = 0.5
    summary['Weighted_Points'] = summary['Present'] + (summary['Late'] * 0.5)
    
    # Formula: (Weighted Points / Total Classes) * 5
    summary['Attendance_Score_5'] = (summary['Weighted_Points'] / summary['Total_Classes']) * 5
    summary['Attendance_Score_5'] = summary['Attendance_Score_5'].round(2)
    
    # Percentage
    summary['Percentage'] = (summary['Weighted_Points'] / summary['Total_Classes']) * 100
    summary['Percentage'] = summary['Percentage'].round(1).astype(str) + "%"

    return summary


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
        if s_id in existing_ids: errors.append(f"Skipped {s_id}"); continue
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
    c1, c2 = st.columns([1, 1.2], gap="large")
    with c1:
        st.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
        # Use a placeholder if logo doesn't exist to prevent error
        try:
            st.image("logo/images.jpeg", width=300)
        except:
            st.warning("Logo not found at logo/images.jpeg")
            
        st.markdown("### Welcome to SGS Pro Connect")
        st.markdown("Streamline your school management with our secure, cloud-synced platform.")
        
    with c2:
        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        st.markdown("<h1 class='login-header'>Login Portal</h1>", unsafe_allow_html=True)
        st.markdown("<p class='slogan-style'>Your School, Connected. Anytime, Anywhere.</p>", unsafe_allow_html=True)
        
        mode = get_data_mode()
        if mode == 'Cloud':
            st.success("✅ System Online (Cloud Connected)")
        else:
            st.warning("⚠️ Offline Mode (Local Database)")
            
        st.markdown("---")
        
        tab1, tab2 = st.tabs(["Staff Login", "Student Portal"])
        with tab1:
            with st.form("staff_login"):
                u = st.text_input("Username", placeholder="e.g. teacher1")
                p = st.text_input("Password", type="password", placeholder="••••••")
                if st.form_submit_button("Sign In"):
                    user = login_staff(u, p)
                    if user:
                        with st.spinner("Authenticating..."): perform_login_sync()
                        st.session_state.logged_in = True
                        st.session_state.user = user
                        st.session_state.role = user[2]
                        st.success(f"Welcome back, {user[0]}!")
                        time.sleep(0.5); st.rerun()
                    else: st.error("Invalid credentials")
            
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
                sid = st.text_input("Student ID", placeholder="e.g. 10101")
                sp = st.text_input("Password", type="password", placeholder="Default is your Student ID")
                if st.form_submit_button("Access Student Portal"):
                    s_user = login_student(sid, sp)
                    if s_user:
                        with st.spinner("Loading Profile..."): perform_login_sync()
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
        
        # Profile Header
        st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
        pic = user_data[3]
        if pic: 
            st.image(Image.open(io.BytesIO(pic)), width=100)
        else: 
            st.image("https://cdn-icons-png.flaticon.com/512/1995/1995539.png" if role != "Student" else "https://cdn-icons-png.flaticon.com/512/3237/3237472.png", width=100)
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown(f"<h3 style='text-align: center; margin-bottom: 0px;'>{user_data[0] if role == 'Teacher' or role == 'Admin' else user_data[1]}</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: center; color: gray;'>{role}</p>", unsafe_allow_html=True)

        if role == "Teacher":
            with st.expander("📷 Change Photo"):
                ukey = st.session_state.uploader_key
                up = st.file_uploader("Up", type=['jpg','png'], label_visibility="collapsed", key=f"t_up_{ukey}")
                if up:
                    img_bytes = up.getvalue()
                    update_teacher_pic(user_data[0], img_bytes)
                    new_user_data = (user_data[0], user_data[1], user_data[2], img_bytes)
                    st.session_state.user = new_user_data
                    st.toast("✅ Photo Updated!")
                    st.session_state.uploader_key += 1
                    time.sleep(1.0); st.rerun()

        st.markdown("---")
        
        if role == "Admin":
            menu = st.radio("Navigation", ["Dashboard", "👥 Manage Teachers", "🎓 Manage Students"])
        elif role == "Teacher":
            menu = st.radio("Navigation", ["Dashboard","📋 Attendance", "📂 Student Roster", "📝 Input Grades", "📊 Gradebook", "👤 Student Record", "⚙️ Settings"])
        else:
            menu = st.radio("Navigation", ["📊 My Attendance","📜 My Grades", "⚙️ Settings"])
        
        st.markdown("---")
        if st.button("🚪 Log Out", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
            
        st.markdown("<p style='text-align: center; font-size: 0.8rem; color: #bbb; margin-top: 20px;'>SGS Pro Connect v2.0</p>", unsafe_allow_html=True)
        
        return menu

# --- PAGE FUNCTIONS ---
def page_dashboard():
    st.title("📊 Dashboard")
    user = st.session_state.user[0]
    
    # 1. FETCH DATA
    subs = get_teacher_subjects_full(user)
    all_active_students = get_all_active_students_list()
    total_system_students = len(all_active_students)
    
    # FETCH GRADES FOR COUNTING
    # We fetch all grades once to accurately count unique students
    all_grades = fetch_all_records("Grades")
    
    subject_details = []
    unique_student_ids_overall = set()
    
    for s_id, s_name in subs:
        # Filter grades for this subject
        s_grades = [g for g in all_grades if g['subject'] == s_name]
        
        # Count unique students for this subject (ignoring multiple quarters)
        unique_s_ids = set(clean_id(g['student_id']) for g in s_grades)
        
        cnt = len(unique_s_ids)
        unique_student_ids_overall.update(unique_s_ids)
        
        subject_details.append((s_id, s_name, cnt))
        
    # Total unique students across all subjects
    my_total_students = len(unique_student_ids_overall)
        
    # 2. METRICS ROW
    c1, c2, c3 = st.columns(3)
    
    # --- UPDATED LABEL HERE ---
    c1.metric("Number of Students", my_total_students, help="Total unique students you teach")
    
    c2.metric("Total Active Students", total_system_students, delta="School Wide")
    c3.metric("System Mode", "Online" if get_data_mode() == 'Cloud' else "Offline")
    
    st.markdown("---")
    
    col_chart, col_subjects = st.columns([2, 1])
    
    with col_chart:
        st.subheader("📈 Student Distribution")
        if not all_active_students.empty:
            chart_data = all_active_students['grade_level'].value_counts().reset_index()
            chart_data.columns = ['Grade Level', 'Count']
            
            c = alt.Chart(chart_data).mark_bar().encode(
                x='Grade Level',
                y='Count',
                color=alt.Color('Grade Level', legend=None),
                tooltip=['Grade Level', 'Count']
            ).properties(height=300)
            st.altair_chart(c, use_container_width=True)
        else:
            st.info("No student data available for charts.")

    with col_subjects:
        st.subheader("📚 My Subjects")
        if not subject_details:
            st.info("You haven't added any subjects yet.")
        else:
            for s_id, s_name, cnt in subject_details:
                with st.expander(f"📘 {s_name}"):
                    st.caption(f"{cnt} Students")
                    c_a, c_b = st.columns([2, 1])
                    new_name = c_a.text_input("Rename", value=s_name, key=f"ren_{s_id}", label_visibility="collapsed")
                    if c_b.button("Save", key=f"btn_ren_{s_id}"):
                        update_subject(s_id, new_name)
                        st.toast("Renamed Successfully!")
                        time.sleep(1); st.rerun()
                    if st.button("Delete", key=f"btn_del_{s_id}", type="primary"):
                        delete_subject(s_id)
                        st.rerun()

    # ADD SUBJECT
    with st.popover("➕ Add New Subject"):
        with st.form("add_sub"):
            new_s = st.text_input("Subject Name", placeholder="e.g. Mathematics M1")
            if st.form_submit_button("Add Subject"):
                if new_s:
                    ok, msg = add_subject(user, new_s)
                    if ok: st.success(msg); time.sleep(1); st.rerun()
                    else: st.error(msg)

def page_admin_dashboard():
    st.title("🛡️ Admin Dashboard")
    u, a, d, t, b, subs = get_admin_stats()
    
    st.markdown("### System Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Users", u)
    c2.metric("Active Students", a)
    c3.metric("Subjects Taught", subs)
    c4.metric("Inactive/Bin", d+t+b)
    
    st.markdown("### Quick Actions")
    st.info("💡 To manage accounts, use the sidebar menu.")


def page_admin_manage_teachers():
    st.title("👥 Manage Teachers")
    teachers = get_all_teachers_with_counts()
    if not teachers.empty: st.dataframe(teachers, width="stretch", hide_index=True)
    else: st.info("No teachers found.")
    
    t1, t2 = st.tabs(["Reset Password", "Delete Teacher"])
    
    with t1:
        with st.form("reset_t_pass"):
            t_user = st.text_input("Username to Reset")
            t_pass = st.text_input("New Password")
            if st.form_submit_button("Reset Password"):
                admin_reset_teacher_password(t_user, t_pass)
                st.success(f"Password for {t_user} reset.")
    
    with t2:
        st.warning("Danger Zone")
        del_t = st.text_input("Enter Username to DELETE")
        if st.button("Permanently Delete Teacher"):
            delete_teacher(del_t)
            st.warning(f"Teacher {del_t} deleted.")
            time.sleep(1); st.rerun()

def page_admin_manage_students():
    st.title("🎓 Manage Students (Admin)")
    tab_list, tab_edit, tab_restore = st.tabs(["📋 Master List", "✏️ Edit / Delete", "♻️ Restore"])
    with tab_list:
        df = get_all_students_admin()
        search = st.text_input("🔍 Search Student", key="adm_search")
        if search: df = df[df['student_name'].str.contains(search, case=False) | df['student_id'].astype(str).str.contains(search)]
        st.dataframe(df, width="stretch", hide_index=True)
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
            st.dataframe(df_del, width="stretch", hide_index=True)
            res_id = st.selectbox("Select Student to Restore", df_del['student_id'].astype(str) + " - " + df_del['student_name'])
            if st.button("♻️ Restore Selected"):
                sid_only = res_id.split(" - ")[0]
                admin_restore_student(sid_only); st.success(f"Student {sid_only} restored!"); time.sleep(1.5); st.rerun()
        else: st.info("Bin is empty.")

def page_roster():
    st.title("📂 Student Roster")
    c1, c2 = st.columns(2)
    with c1: level = st.selectbox("Level", ["M1","M2","M3","M4","M5","M6"])
    with c2: room = st.selectbox("Room", [str(i) for i in range(1,16)])
    
    t1, t2, t3, t4 = st.tabs(["📋 Class List", "➕ Add / Upload", "✏️ Edit / Transfer", "🔍 Search All"])
    
    with t1:
        curr = get_class_roster(level, room, only_active=False)
        if not curr.empty:
            def highlight_status(val):
                if val == 'Active': return 'color: green; font-weight: bold'
                if val == 'Deleted': return 'color: gray; text-decoration: line-through'
                return 'color: red; font-weight: bold'
            st.dataframe(curr[['class_no','student_id','student_name', 'status']].style.map(highlight_status, subset=['status']), hide_index=True, width="stretch")
        else:
            st.info("This class is empty.")

    with t2:
        c_add, c_up = st.columns(2)
        with c_add:
            st.markdown("### Manual Add")
            next_no = get_next_class_no(level, room)
            with st.form("manual_add"):
                m_id = st.text_input("ID")
                m_name = st.text_input("Name")
                m_no = st.number_input("No", value=next_no, disabled=True)
                m_stat = st.selectbox("Status", ["Active", "Transferred"])
                if st.form_submit_button("Add Student"):
                    if m_id and m_name:
                        ok, msg = add_single_student(m_id, m_name, int(m_no), level, room, m_stat)
                        if ok: st.success(msg); time.sleep(1); st.rerun()
                        else: st.error(msg)
        with c_up:
            st.markdown("### Bulk Upload")
            csv = pd.DataFrame({"ID":["10101","10102"], "Name":["Student A","Student B"]}).to_csv(index=False).encode('utf-8')
            st.download_button("⬇️ Template", csv, "template.csv", "text/csv")
            up_file = st.file_uploader("Excel/CSV", type=['xlsx','csv'], key="roster_uploader")
            if up_file and st.button("Upload File"):
                try:
                    df = pd.read_csv(up_file) if up_file.name.endswith('.csv') else pd.read_excel(up_file)
                    ok, msg, errs = upload_roster(df, level, room)
                    if ok: st.success(msg)
                    if errs: st.error(f"{len(errs)} Errors: " + ", ".join(errs[:5]) + "...")
                    time.sleep(1.5); st.rerun()
                except Exception as e: st.error(str(e))
    
    with t3:
        st.markdown("### Edit & Transfer")
        roster = get_class_roster(level, room, only_active=False)
        if not roster.empty:
            edit_target = st.selectbox("Select Student", roster['student_id'] + " - " + roster['student_name'])
            if edit_target:
                s_id = edit_target.split(" - ")[0]
                curr_data = roster[roster['student_id'] == s_id].iloc[0]
                with st.form("edit_stu_details"):
                    e_name = st.text_input("Name", value=curr_data['student_name'])
                    e_no = st.number_input("Class No", value=int(curr_data['class_no']))
                    e_stat = st.selectbox("Status", STUDENT_STATUSES, index=STUDENT_STATUSES.index(curr_data['status']))
                    if st.form_submit_button("Save Changes"):
                        ok, msg = update_student_details(s_id, e_name, int(e_no), e_stat)
                        if ok: st.success(msg); time.sleep(1); st.rerun()
            
            st.divider()
            c_p1, c_p2 = st.columns(2)
            to_lvl = c_p1.selectbox("Promote To Level", ["M1","M2","M3","M4","M5","M6"], key="to_lvl")
            to_rm = c_p2.selectbox("Promote To Room", [str(i) for i in range(1,16)], key="to_rm")
            if st.button(f"🚀 Move ALL Active to {to_lvl}/{to_rm}"):
                ok, msg = promote_students(level, room, to_lvl, to_rm)
                if ok: st.success(msg); time.sleep(1.5); st.rerun()

            if st.button("⚠️ Delete ALL in Class"):
                 ok, msg = soft_delete_class_roster(level, room)
                 if ok: st.warning(msg); time.sleep(1.5); st.rerun()

    with t4:
        search_term = st.text_input("Search Name/ID in School", placeholder="Enter query...")
        if search_term:
            all_studs = get_all_students_admin(include_deleted=True)
            results = all_studs[all_studs['student_name'].str.contains(search_term, case=False) | all_studs['student_id'].astype(str).str.contains(search_term)]
            st.dataframe(results[['student_id', 'student_name', 'grade_level', 'room', 'status']], hide_index=True, width="stretch")

def page_input_grades():
    st.title("📝 Input Grades")
    st.markdown("Record and manage student scores for tests and exams.")

    # --- HELPER: RESET CALLBACKS ---
    # These create the "Safety Chain". If a parent filter changes, children reset.
    
    def reset_from_year():
        # Year changed -> Reset Subject, Quarter, Grade, Room
        for k in ['k_subj', 'k_q', 'k_lvl', 'k_rm']:
            if k in st.session_state: del st.session_state[k]

    def reset_from_subject():
        # Subject changed -> Reset Quarter, Grade, Room
        for k in ['k_q', 'k_lvl', 'k_rm']:
            if k in st.session_state: del st.session_state[k]

    def reset_from_quarter():
        # Quarter changed -> Reset Grade, Room
        for k in ['k_lvl', 'k_rm']:
            if k in st.session_state: del st.session_state[k]

    def reset_from_level():
        # Level changed -> Reset Room
        if 'k_rm' in st.session_state: del st.session_state['k_rm']

    # --- 1. SETUP & DATA FETCHING ---
    subs_raw = get_teacher_subjects_full(st.session_state.user[0])
    subjects = ["Select Subject..."] + [s[1] for s in subs_raw]
    
    if len(subjects) <= 1: 
        st.warning("Please add subjects in Dashboard first.")
        return
    
    # --- SMART SCHOOL YEAR DEFAULT ---
    # Logic: School opens in MAY. 
    # If today is May-Dec (Month 5-12) -> We are in the start year (e.g., 2025).
    # If today is Jan-April (Month 1-4) -> We are in the next year, so start year was last year.
    school_years = get_school_years() # Returns list like ['2024-2025', '2025-2026']
    
    today = datetime.date.today()
    if today.month >= 5: # May or later
        academic_start_year = today.year
    else: # Jan, Feb, Mar, Apr
        academic_start_year = today.year - 1
        
    target_sy_str = f"{academic_start_year}-{academic_start_year+1}"
    
    # Try to find this calculated year in the list to set it as default
    try:
        default_sy_index = school_years.index(target_sy_str)
    except ValueError:
        default_sy_index = 0 # Fallback to first item if not found

    # Fixed Options
    quarters = ["Select Quarter...", "Q1", "Q2", "Q3", "Q4"]
    levels = ["Select Grade...", "M1", "M2", "M3", "M4", "M5", "M6"]
    rooms = ["Select Room..."] + [str(i) for i in range(1, 16)]

    # --- 2. SEQUENTIAL FILTER BAR ---
    with st.container(border=True):
        st.markdown("### 🔎 Select Class Context")
        
        # ROW 1: YEAR & SUBJECT (The most critical filters)
        c_yr, c_sub = st.columns([1, 2])
        
        with c_yr:
            # STEP 1: SCHOOL YEAR
            yr = st.selectbox(
                "📅 School Year",
                school_years,
                index=default_sy_index,
                key="k_yr",
                on_change=reset_from_year
            )
            
        with c_sub:
            # STEP 2: SUBJECT
            subj = st.selectbox(
                "1️⃣ Subject", 
                subjects, 
                key="k_subj", 
                on_change=reset_from_subject
            )

        st.divider()
        
        # ROW 2: QUARTER -> GRADE -> ROOM
        c_q, c_l, c_r = st.columns(3)

        # STEP 3: QUARTER (Disabled until Subject picked)
        with c_q:
            q_disabled = (subj == "Select Subject...")
            q = st.selectbox(
                "2️⃣ Quarter", 
                quarters, 
                key="k_q", 
                disabled=q_disabled, 
                on_change=reset_from_quarter
            )

        # STEP 4: GRADE (Disabled until Quarter picked)
        with c_l:
            lvl_disabled = (q == "Select Quarter..." or q_disabled)
            lvl_sel = st.selectbox(
                "3️⃣ Filter Grade", 
                levels, 
                key="k_lvl", 
                disabled=lvl_disabled,
                on_change=reset_from_level
            )

        # STEP 5: ROOM (Disabled until Grade picked)
        with c_r:
            rm_disabled = (lvl_sel == "Select Grade..." or lvl_disabled)
            rm_sel = st.selectbox(
                "4️⃣ Filter Room", 
                rooms, 
                key="k_rm", 
                disabled=rm_disabled
            )

    # --- 3. LOGIC GATE: ARE FILTERS READY? ---
    filters_complete = (
        subj != "Select Subject..." and 
        q != "Select Quarter..." and 
        lvl_sel != "Select Grade..." and 
        rm_sel != "Select Room..."
    )

    if not filters_complete:
        # Guidance Messages to help the user flow
        if subj == "Select Subject...":
            st.info(f"👆 Confirm School Year is **{yr}**, then select the **Subject**.")
        elif q == "Select Quarter...":
            st.info("👆 Now select the **Quarter**.")
        elif lvl_sel == "Select Grade...":
            st.info("👆 Next, choose the **Grade Level**.")
        elif rm_sel == "Select Room...":
            st.info("👆 Finally, select the **Room Number**.")
        return  # Stop execution here

    # --- 4. LOAD DATA ---
    lvl = lvl_sel
    rm = rm_sel
    
    roster = get_class_roster(lvl, rm, only_active=True)
    if roster.empty: 
        st.warning(f"⚠️ No active students found in **{lvl}/{rm}**.")
        return

    st.success(f"**✅ Active Class:** {len(roster)} students loaded for **{subj}** ({q} - {yr}).")

    # --- 5. TABS FOR TESTS ---
    if "active_test_tab" not in st.session_state: st.session_state.active_test_tab = "Test 1"
    test_options = ["Test 1", "Test 2", "Test 3", "Final Exam", "Bulk Upload"]
    
    try: idx = test_options.index(st.session_state.active_test_tab)
    except: idx = 0
    selected_tab = st.radio("Select Input Mode", test_options, index=idx, horizontal=True)
    st.session_state.active_test_tab = selected_tab
    st.markdown("---")

    # === TEST 1, 2, 3 LOGIC ===
    if selected_tab in ["Test 1", "Test 2", "Test 3"]:
        test_name = selected_tab
        weight = 10.0
        
        active_count = get_enabled_tasks_count(subj, q, yr, test_name)
        
        col_sel, col_add = st.columns([4, 1])
        with col_add:
            if active_count < 10:
                if st.button("➕ Add Task", use_container_width=True):
                    next_t = active_count + 1
                    save_task_max_score(subj, q, yr, test_name, f"Task {next_t}", 0)
                    st.rerun()
        
        with col_sel:
            options = [f"Task {i}" for i in range(1, active_count + 1)]
            options.append("All Tasks (Overview)")
            task_choice = st.radio("Task Selection", options, horizontal=True, label_visibility="collapsed")
        
        total_test_max = get_total_max_score_for_test(subj, q, yr, test_name)

        if task_choice == "All Tasks (Overview)":
            st.info(f"Viewing all tasks for {test_name}. Total Max Score for this test: {int(total_test_max)}")
            existing_tasks = fetch_task_records(subj, q, yr, test_name)
            editor_data = []
            
            for index, row in roster.iterrows():
                sid = str(row['student_id'])
                t_rec = existing_tasks.get(sid, {})
                raw_sum = 0.0
                row_data = {"No": row['class_no'], "ID": sid, "Name": row['student_name']}
                for i in range(1, active_count + 1):
                    val = float(t_rec.get(f't{i}', 0))
                    row_data[f"Task {i}"] = val
                    raw_sum += val
                
                w_score = 0.0
                if total_test_max > 0:
                    w_score = (raw_sum / total_test_max) * weight
                    if w_score > weight: w_score = weight
                
                row_data["Total Raw"] = raw_sum
                row_data["Weighted"] = w_score
                editor_data.append(row_data)
            
            df_editor = pd.DataFrame(editor_data)
            
            col_config = {
                "No": st.column_config.NumberColumn(disabled=True, width="small"),
                "ID": st.column_config.TextColumn(disabled=True),
                "Name": st.column_config.TextColumn(disabled=True),
                "Total Raw": st.column_config.NumberColumn(disabled=True),
                "Weighted": st.column_config.ProgressColumn(min_value=0, max_value=weight, format="%.2f"),
            }
            
            with st.form(key=f"form_{test_name}_all"):
                # FIX: Use width="stretch" instead of use_container_width=True
                edited_df = st.data_editor(
                    df_editor, 
                    hide_index=True, 
                    column_config=col_config, 
                    width="stretch",
                    height=500,
                    disabled=["Weighted", "Total Raw"]
                )
                if st.form_submit_button("💾 Save All & Reset", type="primary"):
                    with st.spinner("Saving..."):
                        ok, msg = save_batch_tasks_and_grades(subj, q, yr, test_name, edited_df, total_test_max, weight, st.session_state.user[0])
                        if ok: 
                            st.success(msg)
                            # RESET FILTERS
                            for k in ['k_subj', 'k_q', 'k_lvl', 'k_rm']:
                                if k in st.session_state: del st.session_state[k]
                            time.sleep(1)
                            st.rerun()

        else:
            # INDIVIDUAL TASK MODE
            current_max = get_task_max_score(subj, q, yr, test_name, task_choice)
            new_max = st.number_input(f"Max Score for {task_choice}", min_value=0.0, value=current_max, step=1.0)
            
            if new_max != current_max:
                save_task_max_score(subj, q, yr, test_name, task_choice, new_max)
                st.rerun()

            if new_max <= 0:
                st.warning(f"⚠️ Set Max Score > 0 to enable grading.")
            else:
                editor_data = []
                t_num = int(task_choice.split(" ")[1])
                task_key = f"t{t_num}"
                existing_tasks = fetch_task_records(subj, q, yr, test_name)
                
                for index, row in roster.iterrows():
                    sid = str(row['student_id'])
                    t_rec = existing_tasks.get(sid, {})
                    current_score = float(t_rec.get(task_key, 0))
                    editor_data.append({
                        "No": row['class_no'], 
                        "ID": sid, 
                        "Name": row['student_name'],
                        task_choice: current_score
                    })
                
                df_editor = pd.DataFrame(editor_data)
                col_config = {
                    "No": st.column_config.NumberColumn(disabled=True, width="small"),
                    "ID": st.column_config.TextColumn(disabled=True),
                    "Name": st.column_config.TextColumn(disabled=True),
                    task_choice: st.column_config.NumberColumn(min_value=0, max_value=int(new_max))
                }
                
                with st.form(key=f"form_{test_name}_{task_choice}"):
                    # FIX: Use width="stretch"
                    edited_df = st.data_editor(df_editor, hide_index=True, column_config=col_config, width="stretch", height=500)
                    if st.form_submit_button(f"💾 Save {task_choice} & Reset", type="primary"):
                        with st.spinner("Saving..."):
                            ok = update_specific_task_column(subj, q, yr, test_name, task_choice, edited_df, st.session_state.user[0], total_test_max, weight)
                            if ok: 
                                st.success("Saved Successfully!")
                                # RESET FILTERS
                                for k in ['k_subj', 'k_q', 'k_lvl', 'k_rm']:
                                    if k in st.session_state: del st.session_state[k]
                                time.sleep(1)
                                st.rerun()

    # === FINAL EXAM LOGIC ===
    elif "Final" in selected_tab:
        st.markdown("### 🏁 Final Exam")
        max_final = st.number_input("Perfect Score", min_value=1.0, value=50.0)
        existing_tasks = fetch_task_records(subj, q, yr, "Final Exam")
        final_data = []
        for index, row in roster.iterrows():
            sid = str(row['student_id'])
            raw_val = float(existing_tasks.get(sid, {}).get('raw_total', 0))
            w_val = 0.0
            if max_final > 0:
                w_val = (raw_val / max_final) * 20.0
                if w_val > 20.0: w_val = 20.0
            final_data.append({"No": row['class_no'], "ID": sid, "Name": row['student_name'], "Raw Score": raw_val, "Weighted (20%)": w_val})
        
        df_final = pd.DataFrame(final_data)
        with st.form("final_form"):
            # FIX: Use width="stretch"
            edited_final = st.data_editor(
                df_final, 
                hide_index=True, 
                column_config={
                    "No": st.column_config.NumberColumn(disabled=True, width="small"),
                    "ID": st.column_config.TextColumn(disabled=True),
                    "Name": st.column_config.TextColumn(disabled=True),
                    "Weighted (20%)": st.column_config.ProgressColumn(min_value=0, max_value=20, format="%.2f")
                }, 
                width="stretch", 
                height=500,
                disabled=["Weighted (20%)"]
            )
            if st.form_submit_button("💾 Save Final Scores & Reset", type="primary"):
                 with st.spinner("Saving..."):
                    ok = save_final_exam_batch(subj, q, yr, edited_final, max_final, st.session_state.user[0])
                    if ok: 
                        st.success("Saved Successfully!")
                        # RESET FILTERS
                        for k in ['k_subj', 'k_q', 'k_lvl', 'k_rm']:
                            if k in st.session_state: del st.session_state[k]
                        time.sleep(1)
                        st.rerun()

    # === BULK UPLOAD LOGIC ===
    elif selected_tab == "Bulk Upload":
        st.markdown("### 📤 Excel Upload")
        target_test = st.selectbox("Select Target", ["Test 1", "Test 2", "Test 3", "Final Exam"])
        weight = 20.0 if target_test == "Final Exam" else 10.0
        upload_max_score = st.number_input(f"Total Max Raw Score for {target_test}", min_value=1.0, value=50.0)
        
        if st.button("⬇️ Download Template"):
            tmp = roster[['class_no', 'student_id', 'student_name']].copy()
            tmp = tmp.rename(columns={'student_id': 'ID', 'student_name': 'Name'})
            for i in range(1, 11): tmp[f'Task {i}'] = 0
            
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                tmp.to_excel(writer, index=False)
            st.download_button("Download .xlsx", out.getvalue(), "template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            
        up_file = st.file_uploader("Upload Excel", type=['xlsx'])
        if up_file and st.button("Process Upload"):
            try:
                df = pd.read_excel(up_file)
                if "Student ID" in df.columns: df = df.rename(columns={"Student ID": "ID"})
                ok, msg = save_batch_tasks_and_grades(subj, q, yr, target_test, df, upload_max_score, weight, st.session_state.user[0])
                if ok: 
                    st.success(msg)
                    # RESET FILTERS
                    for k in ['k_subj', 'k_q', 'k_lvl', 'k_rm']:
                        if k in st.session_state: del st.session_state[k]
                    time.sleep(1.5)
                    st.rerun()
                else: st.error(msg)
            except Exception as e: st.error(f"Error: {e}")

def page_gradebook():
    st.title("📊 Gradebook")
    
    # 1. Select Subject
    subs_raw = get_teacher_subjects_full(st.session_state.user[0])
    subjects = [s[1] for s in subs_raw]
    
    if not subjects: 
        st.warning("No subjects assigned to you.")
        return
    
    school_years = get_school_years()
    
    # 2. Filters
    c1,c2,c3,c4 = st.columns(4)
    s = c1.selectbox("Subject", subjects)
    l = c2.selectbox("Level", ["M1","M2","M3","M4","M5","M6"])
    r = c3.selectbox("Room", [str(i) for i in range(1,16)])
    q = c4.selectbox("Quarter", ["Q1","Q2","Q3","Q4"])
    
    # Get the current school year
    yr = school_years[1] 
    
    # 3. Get Student Roster
    roster = get_class_roster(l, r, only_active=True)
    if roster.empty: 
        st.info("No students found in this class.")
        return
        
    data = []
    
    # 4. Build Table (WITHOUT GPA)
    for idx, row in roster.iterrows():
        sid = str(row['student_id'])
        rec = get_grade_record(sid, s, q, yr)
        
        if rec:
            t1, t2, t3, fin, tot = rec
            # GPA Calculation Removed
            data.append({
                "No": row['class_no'], 
                "Name": row['student_name'], 
                "Test 1": fmt_score(float(t1)), 
                "Test 2": fmt_score(float(t2)), 
                "Test 3": fmt_score(float(t3)), 
                "Final": fmt_score(float(fin)), 
                "Total": fmt_score(float(tot))
            })
        else:
             data.append({
                 "No": row['class_no'], 
                 "Name": row['student_name'], 
                 "Test 1": "-", 
                 "Test 2": "-", 
                 "Test 3": "-", 
                 "Final": "-", 
                 "Total": "-"
             })
    
    # 5. Display Table
    st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)
    
    # 6. Export to Excel (WITHOUT GPA)
    if data:
        export_data = []
        for row in data:
            # We explicitly define the columns here to exclude GPA
            export_data.append({
                "No.": row["No"],
                "Name": row["Name"],
                "Test 1(10)": row["Test 1"],
                "Test 2(10)": row["Test 2"],
                "Test 3(10)": row["Test 3"],
                "Final(20)": row["Final"],
                "Total(50)": row["Total"]
            })
        
        df_export = pd.DataFrame(export_data)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, index=False, sheet_name="Gradebook")
            
        st.download_button(
            label="⬇️ Download Excel",
            data=buffer.getvalue(),
            file_name=f"Gradebook_{s}_{l}_{r}_{q}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
def page_student_dashboard():
    # --- HEADER ---
    st.title(f"📊 My Attendance")
    
    if 'user' not in st.session_state:
        st.warning("Please log in first.")
        return

    # 1. Get Logged-in Student ID (Cleaned)
    raw_id = st.session_state.user[0]
    my_id = str(raw_id).strip().replace(".0", "")
    
    st.markdown(f"**Welcome, {st.session_state.user[1]}**")

    # 2. Fetch Attendance Data
    all_att = fetch_all_records("Attendance")
    
    # --- HELPER: Smart Column Finder ---
    def get_col_value(row, targets):
        keys = list(row.keys())
        # 1. Exact match
        for t in targets:
            if t in row: return row[t]
        # 2. Case-insensitive match
        for k in keys:
            for t in targets:
                if k.lower().strip() == t.lower().strip():
                    return row[k]
        return None

    # 3. Filter Records for THIS Student
    my_records = []
    for r in all_att:
        row_id_val = get_col_value(r, ["student_id", "Student ID", "Student_ID", "ID", "id"])
        if row_id_val is not None:
            db_id = str(row_id_val).strip().replace(".0", "")
            if db_id == my_id:
                my_records.append(r)

    # --- MAIN DISPLAY ---
    if not my_records:
        st.info("👋 You have no attendance records yet. Check back after your first class!")
    else:
        # Get list of subjects
        subjects_set = set()
        for r in my_records:
            s = get_col_value(r, ["subject", "Subject", "Subject Name"])
            if s: subjects_set.add(s)
        
        my_subjects = sorted(list(subjects_set))
        
        if not my_subjects:
            st.error("⚠️ Error: Found your records, but the 'Subject' column is missing in the database.")
        else:
            # Subject Selector
            c_sel, _ = st.columns([1, 2])
            with c_sel:
                selected_sub = st.selectbox("Select Subject", my_subjects)
            
            # Filter for this subject
            sub_recs = []
            for r in my_records:
                s = get_col_value(r, ["subject", "Subject", "Subject Name"])
                if s == selected_sub:
                    sub_recs.append(r)
            
            # Calculate Stats
            n_present = 0
            n_late = 0
            n_absent = 0
            total = len(sub_recs)
            
            for r in sub_recs:
                st_val = str(get_col_value(r, ["status", "Status", "attendance"])).lower()
                if "present" in st_val: n_present += 1
                elif "late" in st_val: n_late += 1
                elif "absent" in st_val: n_absent += 1
            
            # Math: Present=100%, Late=50%, Absent=0%
            weighted = n_present + (n_late * 0.5)
            
            score = 0.0
            pct = 0.0
            if total > 0:
                score = (weighted / total) * 5.0
                pct = (weighted / total) * 100.0
            
            # --- CARDS ---
            st.markdown("### Overview")
            c1, c2, c3 = st.columns(3)
            c1.metric("Score (Max 5)", f"{score:.2f}")
            c2.metric("Attendance Rate", f"{pct:.1f}%")
            c3.metric("Classes Held", total)
            
            # Progress Bar Color Logic
            if pct >= 80: bar_color = "green"
            elif pct >= 60: bar_color = "orange"
            else: bar_color = "red"
            
            st.caption(f"Progress ({pct:.1f}%)")
            st.progress(min(score/5.0, 1.0))
            
            # Warning if attendance is low
            if pct < 60:
                st.warning(f"⚠️ Your attendance is {pct:.1f}%. Please try to attend more classes!")

            # --- HISTORY TABLE ---
            st.markdown("---")
            st.markdown(f"### 📜 History: {selected_sub}")
            
            # Prepare clean table
            table_data = []
            for r in sub_recs:
                table_data.append({
                    "Date": get_col_value(r, ["date", "Date", "day"]),
                    "Status": get_col_value(r, ["status", "Status"]),
                    "Teacher": get_col_value(r, ["recorded_by", "Teacher", "Recorded By"])
                })
            
            df_show = pd.DataFrame(table_data)
            if not df_show.empty and "Date" in df_show.columns:
                    df_show = df_show.sort_values(by="Date", ascending=False)
            
            # Use st.dataframe with custom height for a pro look
            st.dataframe(
                df_show, 
                use_container_width=True, 
                hide_index=True,
                height=300
            )
def page_student_record_teacher_view():
    st.title("👤 Student Record & Academic History")
    
    # --- 1. FETCH STUDENTS ---
    students_data = fetch_all_records("Students")
    df = pd.DataFrame(students_data)
    
    if df.empty:
        st.warning("No students found in database.")
        return
        
    if 'status' in df.columns:
        df = df[df['status'] != 'Deleted']
    
    # --- 2. SEARCH & FILTER SECTION ---
    with st.container(border=True):
        st.markdown("### 🔍 Find Student")
        
        # A. Global Search Bar
        search_term = st.text_input("🔎 Search by Name or ID", placeholder="Type name or ID (e.g., '1001' or 'John')...").strip()
        
        df_filtered = df.copy()
        
        # Logic: If searching, ignore dropdowns. If not searching, use dropdowns.
        if search_term:
            # Filter by Name OR ID
            mask = (
                df['student_name'].astype(str).str.contains(search_term, case=False) | 
                df['student_id'].astype(str).str.contains(search_term, case=False)
            )
            df_filtered = df[mask]
            st.caption(f"Found {len(df_filtered)} matches for '{search_term}'")
            
        else:
            # B. Dropdown Filters (Only used if search is empty)
            all_grades = ["All Grades"] + sorted(df['grade_level'].astype(str).unique().tolist())
            all_rooms = ["All Rooms"] + sorted(df['room'].astype(str).unique().tolist())
            
            c1, c2 = st.columns(2)
            with c1: sel_grade = st.selectbox("Filter by Grade", all_grades)
            with c2: sel_room = st.selectbox("Filter by Room", all_rooms)
            
            if sel_grade != "All Grades":
                df_filtered = df_filtered[df_filtered['grade_level'].astype(str) == sel_grade]
            if sel_room != "All Rooms":
                df_filtered = df_filtered[df_filtered['room'].astype(str) == sel_room]

        # C. Student Selector
        # Format list as: "Name (ID)"
        df_filtered['display'] = df_filtered['student_name'] + " (" + df_filtered['student_id'].astype(str) + ")"
        student_opts = sorted(df_filtered['display'].tolist())
        
        # Auto-select if only 1 match found during search
        idx = 0
        if len(student_opts) == 1:
            idx = 0
        
        selected_student_str = st.selectbox("Select Student Profile", student_opts, index=idx)

    # --- 3. DISPLAY PROFILE ---
    if selected_student_str:
        # Extract ID
        sel_id = selected_student_str.split("(")[-1].replace(")", "")
        student_rec = df[df['student_id'].astype(str) == sel_id].iloc[0]
        
        st.markdown("---")
        
        # LAYOUT: Photo (Left) | Details (Right)
        col_img, col_info = st.columns([1, 3])
        
        with col_img:
            img_data = base64_to_image(student_rec.get('photo', ''))
            if img_data:
                st.image(img_data, width=180, caption=f"ID: {sel_id}")
            else:
                st.markdown(
                    f"""<div style='width:180px; height:180px; background-color:#f0f2f6; 
                    border-radius:10px; display:flex; align-items:center; justify-content:center;
                    font-size:50px; color:#ccc;'>👤</div>""", 
                    unsafe_allow_html=True
                )
                
        with col_info:
            st.subheader(f"{student_rec['student_name']}")
            
            # Badge Details
            b1, b2, b3 = st.columns(3)
            with b1: st.info(f"**Grade:** {student_rec['grade_level']}")
            with b2: st.info(f"**Room:** {student_rec['room']}")
            with b3: st.success(f"**Status:** {student_rec.get('status', 'Active')}")
            
            st.write(f"**Class No:** {student_rec.get('class_no', '-')}")
            
        # --- 4. GRADES TABLE ---
        st.markdown("### 📚 Academic History")
        all_grades = fetch_all_records("Grades")
        # Filter grades for this student
        student_grades = [g for g in all_grades if str(g['student_id']).strip().replace(".0","") == str(sel_id)]
        
        if student_grades:
            df_g = pd.DataFrame(student_grades)
            # Pick columns
            cols = ['subject', 'school_year', 'quarter', 'test1', 'test2', 'test3', 'final_score', 'total_score']
            cols = [c for c in cols if c in df_g.columns]
            
            # Rename
            rename = {'subject':'Subject', 'school_year':'Year', 'quarter':'Q', 
                      'test1':'Test 1', 'test2':'Test 2', 'test3':'Test 3', 
                      'final_score':'Final', 'total_score':'Total'}
            
            st.dataframe(df_g[cols].rename(columns=rename), use_container_width=True, hide_index=True)
        else:
            st.caption("No grades recorded yet.")
            
        # --- 5. ATTENDANCE SUMMARY ---
        st.markdown("### 📅 Attendance Overview")
        all_att = fetch_all_records("Attendance")
        my_att = [r for r in all_att if str(r.get('student_id','')).strip().replace(".0","") == str(sel_id)]
        
        if my_att:
            df_a = pd.DataFrame(my_att)
            # Simple counts
            # Normalize keys to handle "🟢 Present" vs "Present"
            s = df_a['status'].astype(str)
            n_pres = s.str.contains("Present|🟢").sum()
            n_abs  = s.str.contains("Absent|🔴").sum()
            n_late = s.str.contains("Late|🟡").sum()
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Present", int(n_pres))
            k2.metric("Absent", int(n_abs))
            k3.metric("Late", int(n_late))
        else:
            st.caption("No attendance records found.")

def page_attendance():
    st.title("📋 Attendance Manager")
    st.markdown("Manage daily class registers and generate official attendance reports.")
    
    # --- HELPER: RESET CALLBACKS ---
    def reset_daily_filters():
        if 'daily_grade' in st.session_state: del st.session_state.daily_grade
        if 'daily_room' in st.session_state: del st.session_state.daily_room

    def reset_report_filters():
        if 'rep_grade' in st.session_state: del st.session_state.rep_grade
        if 'rep_room' in st.session_state: del st.session_state.rep_room

    # --- FETCH DATA ---
    subs_data = fetch_all_records("Subjects")
    subjects = ["Select Subject..."] + sorted(list(set([s['subject_name'] for s in subs_data])))
    
    students_data = fetch_all_records("Students")
    df_students = pd.DataFrame(students_data)
    if not df_students.empty and 'status' in df_students.columns:
        df_students = df_students[df_students['status'] != 'Deleted']
    
    all_att = fetch_all_records("Attendance")
    df_att = pd.DataFrame(all_att)

    if len(subjects) <= 1: 
        st.error("🚫 **System Error:** No subjects found. Please contact the administrator.")
        return

    # --- TABS ---
    tab1, tab2 = st.tabs(["📝 Daily Register (Editor)", "📊 Reports & Corrections"])
    
    # ==========================================
    # TAB 1: DAILY REGISTER
    # ==========================================
    with tab1:
        st.markdown("### 📅 Daily Class Register")
        st.caption("Follow the steps in order to unlock the class list.")
        
        with st.container(border=True):
            # STEP 1: SUBJECT & DATE
            c1, c2 = st.columns(2)
            with c1: 
                selected_sub = st.selectbox(
                    "1️⃣ Select Subject", 
                    subjects, 
                    key="att_sub_daily",
                    on_change=reset_daily_filters 
                )
            with c2: 
                date_val = st.date_input("Date", datetime.date.today())
            
            st.markdown("---")
            
            # STEP 2 & 3: GRADE & ROOM
            # Fix: Sort levels naturally (M1, M2... not M1, M10, M2)
            unique_grades = sorted(df_students['grade_level'].unique().astype(str).tolist())
            all_grades = ["Select Grade..."] + unique_grades
            
            # Simple room sort is fine for numbers 1-15
            all_rooms = ["Select Room..."] + sorted(df_students['room'].unique().astype(str).tolist(), key=lambda x: int(x) if x.isdigit() else x)

            f1, f2, f3 = st.columns([1, 1, 2])
            
            with f1:
                grade_disabled = (selected_sub == "Select Subject...")
                sel_grade = st.selectbox("2️⃣ Filter Grade", all_grades, key="daily_grade", disabled=grade_disabled)
            
            with f2:
                room_disabled = (sel_grade == "Select Grade...")
                sel_room = st.selectbox("3️⃣ Filter Room", all_rooms, key="daily_room", disabled=room_disabled)

        # LOGIC: ARE WE READY?
        filters_complete = (selected_sub != "Select Subject..." and sel_grade != "Select Grade..." and sel_room != "Select Room...")
        
        if not filters_complete:
            if selected_sub == "Select Subject...":
                st.info("👆 Please start by selecting a **Subject**.")
            elif sel_grade == "Select Grade...":
                st.info("👆 Good! Now select the **Grade Level**.")
            elif sel_room == "Select Room...":
                st.info("👆 Almost there! Select the **Room Number**.")
        else:
            # 3. SHOW DATA
            mask = (df_students['grade_level'].astype(str) == sel_grade) & (df_students['room'].astype(str) == sel_room)
            df_filtered = df_students[mask].sort_values(by=["student_name"])

            with f3:
                st.success(f"**✅ Class Loaded:** {len(df_filtered)} students")

            if df_filtered.empty:
                st.warning("⚠️ No students found in this Grade/Room.")
            else:
                existing_map = {}
                if not df_att.empty:
                    day_records = df_att[(df_att['date'].astype(str) == str(date_val)) & (df_att['subject'] == selected_sub)]
                    for _, r in day_records.iterrows():
                        existing_map[str(r['student_id']).replace(".0","")] = r.get('status', 'Present')

                editor_rows = []
                STATUS_OPTS = ["🟢 Present", "🔴 Absent", "🟡 Late", "⚪ Excused"]
                
                for i, (_, s) in enumerate(df_filtered.iterrows(), 1):
                    sid = str(s['student_id']).replace(".0","")
                    current_status = existing_map.get(sid, "Present")
                    
                    # Normalization logic
                    if "Present" in current_status and "🟢" not in current_status: disp_status = "🟢 Present"
                    elif "Absent" in current_status and "🔴" not in current_status: disp_status = "🔴 Absent"
                    elif "Late" in current_status and "🟡" not in current_status: disp_status = "🟡 Late"
                    elif "Excused" in current_status and "⚪" not in current_status: disp_status = "⚪ Excused"
                    else: disp_status = current_status

                    editor_rows.append({
                        "No.": i,
                        "Student_ID": sid,
                        "Name": s['student_name'],
                        "Grade_level": s['grade_level'],
                        "Room": s['room'],
                        "Status": disp_status
                    })
                
                df_edit = pd.DataFrame(editor_rows)
                
                st.info(f"📝 Editing Register for: **{date_val.strftime('%B %d, %Y')}**")
                
                # --- FIX IS HERE ---
                # Replaced 'use_container_width=True' with 'width="stretch"' for st.dataframe if needed, 
                # but for data_editor specifically, we rely on default width behavior or just remove the param if strict.
                # However, to fix your specific error log, we remove 'use_container_width' and use the layout to control width.
                edited_df = st.data_editor(
                    df_edit,
                    column_config={
                        "No.": st.column_config.NumberColumn("No.", width="small", disabled=True),
                        "Student_ID": st.column_config.TextColumn("ID", width="small", disabled=True),
                        "Name": st.column_config.TextColumn("Name", disabled=True),
                        "Grade_level": st.column_config.TextColumn("Grade", width="small", disabled=True),
                        "Room": st.column_config.TextColumn("Room", width="small", disabled=True),
                        "Status": st.column_config.SelectboxColumn("Status", options=STATUS_OPTS, required=True, width="medium")
                    },
                    hide_index=True,
                    use_container_width=True, # Keeping this IF your streamlit version supports it, otherwise remove it.
                    # If you still see errors, DELETE the line above.
                    height=500
                )
                
                if st.button("💾 Save Attendance & Reset", type="primary", use_container_width=True):
                    try:
                        teacher = st.session_state.user[0]
                        timestamp = str(datetime.datetime.now())
                        # Note: fetch_all_records is slow if DB is big. In production, filter in query.
                        current_db = fetch_all_records("Attendance")
                        
                        ids_to_update = edited_df['Student_ID'].astype(str).tolist()
                        
                        final_list = []
                        # Optimized cleaning loop
                        for r in current_db:
                            is_same_day = (str(r.get('date')) == str(date_val))
                            is_same_sub = (r.get('subject') == selected_sub)
                            sid = str(r.get('student_id')).replace(".0","")
                            
                            # Keep record only if it's NOT the one we are updating
                            if not (is_same_day and is_same_sub and sid in ids_to_update):
                                final_list.append(r)
                        
                        for _, row in edited_df.iterrows():
                            clean_stat = row['Status'].split(" ")[1] if " " in row['Status'] else row['Status']
                            new_rec = {
                                "uid": f"{date_val}_{selected_sub}_{row['Student_ID']}",
                                "student_id": row['Student_ID'],
                                "student_name": row['Name'],
                                "subject": selected_sub,
                                "date": str(date_val),
                                "status": clean_stat,
                                "recorded_by": teacher,
                                "timestamp": timestamp
                            }
                            final_list.append(new_rec)
                            
                        overwrite_sheet_data("Attendance", final_list)
                        st.success("✅ **Saved Successfully!** Resetting page...")
                        
                        reset_daily_filters()
                        if 'att_sub_daily' in st.session_state: del st.session_state.att_sub_daily
                        
                        time.sleep(1)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Error: {e}")

    # ==========================================
    # TAB 2: REPORTS
    # ==========================================
    with tab2:
        st.markdown("### 📊 Reports & Corrections")
        
        with st.container(border=True):
            view_sub = st.selectbox(
                "1️⃣ Select Subject", 
                subjects, 
                key="view_att_sub",
                on_change=reset_report_filters
            )
            
            all_grades_rep = ["Select Grade..."] + sorted(df_students['grade_level'].unique().astype(str).tolist())
            all_rooms_rep = ["Select Room..."] + sorted(df_students['room'].unique().astype(str).tolist(), key=lambda x: int(x) if x.isdigit() else x)
            
            rc1, rc2 = st.columns(2)
            with rc1:
                g_rep_disabled = (view_sub == "Select Subject...")
                f_grade = st.selectbox("2️⃣ Filter Grade", all_grades_rep, key="rep_grade", disabled=g_rep_disabled)
            with rc2:
                r_rep_disabled = (f_grade == "Select Grade...")
                f_room = st.selectbox("3️⃣ Filter Room", all_rooms_rep, key="rep_room", disabled=r_rep_disabled)

        rep_ready = (view_sub != "Select Subject..." and f_grade != "Select Grade..." and f_room != "Select Room...")

        if not rep_ready:
             if view_sub == "Select Subject...":
                 st.info("👆 Please select a **Subject**.")
             elif f_grade == "Select Grade...":
                st.info("👆 Now select a **Grade Level**.")
             elif f_room == "Select Room...":
                st.info("👆 Finally, select the **Room**.")
        else:
            if st.button("Generate Report", type="primary"):
                st.session_state.report_generated = True
            
            if st.session_state.get('report_generated', False):
                stats = get_attendance_score_data(view_sub)
                
                if not stats.empty:
                    df_info = df_students[['student_id', 'student_name', 'grade_level', 'room']].copy()
                    df_info['student_id'] = df_info['student_id'].astype(str).str.replace(".0","").str.strip()
                    stats.index = stats.index.astype(str)
                    
                    full_report = pd.merge(df_info, stats, left_on="student_id", right_index=True, how="right")
                    
                    full_report = full_report[full_report['grade_level'].astype(str) == f_grade]
                    full_report = full_report[full_report['room'].astype(str) == f_room]
                    
                    if full_report.empty:
                        st.warning("No students match these filters.")
                    else:
                        full_report.insert(0, 'No.', range(1, 1 + len(full_report)))
                        full_report = full_report.rename(columns={'student_id': 'Student_ID', 'student_name': 'Name', 'grade_level': 'Grade_level', 'room': 'Room'})
                        
                        # Fix: Replaced use_container_width with correct approach for dataframe
                        st.dataframe(
                            full_report[['No.', 'Student_ID', 'Name', 'Grade_level', 'Room', 'Present', 'Absent', 'Percentage', 'Attendance_Score_5']],
                            column_config={
                                "No.": st.column_config.NumberColumn("No.", width="small"),
                                "Student_ID": st.column_config.TextColumn("ID", width="small"),
                                "Attendance_Score_5": st.column_config.ProgressColumn("Score", format="%.2f", min_value=0, max_value=5),
                            },
                            use_container_width=True, 
                            hide_index=True
                        )
                        
                        st.markdown("---")
                        st.markdown("### 📤 Export")
                        with st.container(border=True):
                            e1, e2, e3 = st.columns([1, 1, 1])
                            with e1: target_col = st.selectbox("Save to:", ["Select...", "Test 1", "Test 2", "Test 3"])
                            with e2: target_q = st.selectbox("Quarter", ["Q1", "Q2", "Q3", "Q4"])
                            with e3: target_sy = st.selectbox("School Year", get_school_years(), index=1)
                            
                            if target_col != "Select...":
                                if st.button(f"💾 Save to {target_col}", type="primary"):
                                    full_report['student_id'] = full_report['Student_ID'] 
                                    save_attendance_to_grades(full_report, view_sub, target_q, target_sy, target_col)
                else:
                    st.info("No records found.")


# --- HELPER: SAVE FUNCTION (Paste this OUTSIDE page_attendance) ---
def save_attendance_to_grades(report_df, subject, quarter, year, target_test):
    """
    Saves the 'Attendance_Score_5' column into the Grades table.
    """
    # 1. Map "Test 1" -> "test1" (database column name)
    col_map = {"Test 1": "test1", "Test 2": "test2", "Test 3": "test3"}
    db_col = col_map.get(target_test)
    
    if not db_col: return

    # 2. Fetch existing grades
    all_grades = fetch_all_records("Grades")
    teacher = st.session_state.user[0]
    timestamp = str(datetime.datetime.now())
    
    # 3. Update Logic
    updated_count = 0
    
    # Convert report to a dictionary for fast lookup: {student_id: score}
    score_map = dict(zip(report_df['student_id'].astype(str), report_df['Attendance_Score_5']))
    
    # Track which IDs we have processed
    processed_ids = []
    
    # A. Update existing rows
    for row in all_grades:
        # Check if row matches Subject + Quarter + Year
        if row['subject'] == subject and row['quarter'] == quarter and row['school_year'] == year:
            sid = str(row['student_id']).strip().replace(".0", "")
            
            if sid in score_map:
                # UPDATE THE SCORE
                row[db_col] = float(score_map[sid])
                
                # Recalculate Total
                t1 = float(row.get('test1', 0) or 0)
                t2 = float(row.get('test2', 0) or 0)
                t3 = float(row.get('test3', 0) or 0)
                fin = float(row.get('final_score', 0) or 0)
                row['total_score'] = t1 + t2 + t3 + fin
                
                row['recorded_by'] = teacher
                row['timestamp'] = timestamp
                
                processed_ids.append(sid)
                updated_count += 1
    
    # B. Create NEW rows for students who don't have a grade row yet
    for sid, score in score_map.items():
        if sid not in processed_ids:
            new_row = {
                "id": int(time.time()) + int(sid), # Unique ID
                "student_id": sid,
                "subject": subject,
                "quarter": quarter,
                "school_year": year,
                "test1": 0, "test2": 0, "test3": 0, "final_score": 0,
                "total_score": 0,
                "recorded_by": teacher,
                "timestamp": timestamp
            }
            # Set the specific test score
            new_row[db_col] = float(score)
            new_row['total_score'] = float(score)
            
            all_grades.append(new_row)
            updated_count += 1
            
    # 4. Save to Database
    with st.spinner("Saving scores to Gradebook..."):
        overwrite_sheet_data("Grades", all_grades)
        
    st.success(f"✅ Successfully exported scores for {updated_count} students to {target_test}!")
    time.sleep(2)
    st.rerun()


def page_teacher_settings():
    st.title("⚙️ Settings")
    current_u = st.session_state.user[0]
    current_p = st.session_state.user[1]
    
    with st.container():
        st.subheader("Security")
        with st.form("teach_settings"):
            new_u = st.text_input("Username", value=current_u)
            new_p = st.text_input("Password", value=current_p, type="password")
            if st.form_submit_button("Update Credentials"):
                if new_u and new_p:
                    with st.spinner("Updating..."):
                        ok, msg = update_teacher_credentials(current_u, new_u, new_p)
                        if ok: st.success(msg); st.session_state.logged_in = False; time.sleep(2); st.rerun()
                        else: st.error(msg)
                else: st.warning("Fields cannot be empty.")
def page_student_portal_grades():
    s_data = st.session_state.user
    s_id = str(s_data[0]) # Ensure string format
    s_name = s_data[1]
    
    st.title(f"👋 Hello, {s_name}")
    st.caption(f"Student ID: {s_id}")

    # --- HELPER: GPA SCALE ---
    def get_sem_gpa(score):
        if score >= 80: return 4.0
        elif score >= 75: return 3.5
        elif score >= 70: return 3.0
        elif score >= 65: return 2.5
        elif score >= 60: return 2.0
        elif score >= 55: return 1.5
        elif score >= 50: return 1.0
        else: return 0.0

    # --- 1. REPORT CARD SECTION ---
    st.header("📜 Report Card")
    
    # Fetch all grades
    all_grades = fetch_all_records("Grades")
    # Filter for this student
    my_grades = [g for g in all_grades if clean_id(g['student_id']) == s_id]

    if not my_grades:
        st.info("No academic records found.")
    else:
        df_grades = pd.DataFrame(my_grades)
        
        # Group by School Year (Newest first)
        unique_years = sorted(df_grades['school_year'].unique(), reverse=True)
        
        for yr in unique_years:
            with st.container():
                st.subheader(f"📅 School Year: {yr}")
                
                # Filter for this year
                year_data = df_grades[df_grades['school_year'] == yr]
                subjects = year_data['subject'].unique()
                
                report_card_data = []
                
                for sub in subjects:
                    # Get entries for this subject
                    sub_entries = year_data[year_data['subject'] == sub]
                    
                    # Teacher Name (from most recent entry)
                    teacher = sub_entries.iloc[0]['recorded_by'] if not sub_entries.empty else "-"

                    # Extract Quarters
                    def get_score(q_name):
                        row = sub_entries[sub_entries['quarter'] == q_name]
                        return float(row.iloc[0]['total_score']) if not row.empty else 0.0
                    
                    q1 = get_score("Q1")
                    q2 = get_score("Q2")
                    q3 = get_score("Q3")
                    q4 = get_score("Q4")
                    
                    # Calculate Semesters
                    sem1_total = q1 + q2
                    sem1_gpa = get_sem_gpa(sem1_total)
                    
                    sem2_total = q3 + q4
                    sem2_gpa = get_sem_gpa(sem2_total)
                    
                    report_card_data.append({
                        "Subject": sub,
                        "Teacher": teacher,
                        "Q1": fmt_score(q1),
                        "Q2": fmt_score(q2),
                        "1st Sem Total": fmt_score(sem1_total),
                        "1st Sem GPA": f"{sem1_gpa:.1f}",
                        "Q3": fmt_score(q3),
                        "Q4": fmt_score(q4),
                        "2nd Sem Total": fmt_score(sem2_total),
                        "2nd Sem GPA": f"{sem2_gpa:.1f}"
                    })
                
                if report_card_data:
                    df_display = pd.DataFrame(report_card_data)
                    
                    # Display Table
                    st.dataframe(
                        df_display,
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Subject": st.column_config.TextColumn("Subject", width="medium"),
                            "Teacher": st.column_config.TextColumn("Teacher", width="small"),
                            "Q1": st.column_config.TextColumn("Q1", width="small"),
                            "Q2": st.column_config.TextColumn("Q2", width="small"),
                            "1st Sem Total": st.column_config.TextColumn("Sem 1 Score", width="small", help="Sum of Q1 + Q2"),
                            "1st Sem GPA": st.column_config.TextColumn("Sem 1 GPA", width="small"),
                            "Q3": st.column_config.TextColumn("Q3", width="small"),
                            "Q4": st.column_config.TextColumn("Q4", width="small"),
                            "2nd Sem Total": st.column_config.TextColumn("Sem 2 Score", width="small", help="Sum of Q3 + Q4"),
                            "2nd Sem GPA": st.column_config.TextColumn("Sem 2 GPA", width="small"),
                        }
                    )
                    
                    # DOWNLOAD BUTTON
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                        df_display.to_excel(writer, index=False, sheet_name=f"Report_{yr}")
                    
                    st.download_button(
                        label=f"⬇️ Download Report Card ({yr})",
                        data=buffer.getvalue(),
                        file_name=f"Report_Card_{s_name}_{yr}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.caption("No grades recorded for this year.")
                st.divider()

    # --- 2. TASK BREAKDOWN SECTION ---
    st.header("📊 Task Breakdown")
    
    # Fetch all tasks
    all_tasks = fetch_all_records("Tasks")
    my_tasks = [t for t in all_tasks if clean_id(t['student_id']) == s_id]
    
    if not my_tasks:
        st.info("No detailed tasks found.")
    else:
        df_tasks = pd.DataFrame(my_tasks)
        
        # Group by School Year
        task_years = sorted(df_tasks['school_year'].unique(), reverse=True)
        
        for yr in task_years:
            with st.expander(f"📅 Tasks for School Year: {yr}", expanded=False):
                yr_tasks = df_tasks[df_tasks['school_year'] == yr]
                
                # Group by Subject
                unique_subs = yr_tasks['subject'].unique()
                
                for sub in unique_subs:
                    st.markdown(f"**📘 {sub}**")
                    sub_tasks = yr_tasks[yr_tasks['subject'] == sub]
                    
                    # Simplify columns for display
                    # Showing Test Name, Quarter, and Raw Score
                    display_cols = sub_tasks[['quarter', 'test_name', 'raw_total']]
                    display_cols.columns = ['Quarter', 'Task / Exam Name', 'My Score']
                    
                    st.dataframe(
                        display_cols, 
                        hide_index=True, 
                        use_container_width=True
                    )
                    st.write("") # Spacer


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
        elif sel == "📋 Attendance": page_attendance()
        elif sel == "📝 Input Grades": page_input_grades()
        elif sel == "📊 Gradebook": page_gradebook()
        elif sel == "👤 Student Record": page_student_record_teacher_view()
        elif sel == "⚙️ Settings": page_teacher_settings()
    else:
        if sel == "📊 My Attendance": page_student_dashboard()
        if sel == "📜 My Grades": page_student_portal_grades()
        elif sel == "⚙️ Settings": page_student_settings()