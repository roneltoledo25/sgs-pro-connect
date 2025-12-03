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
            menu = st.radio("Navigation", ["📜 My Grades", "⚙️ Settings"])
        
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
    c_a, c_b = st.columns(2)
    with c_a:
        st.info("💡 To manage accounts, use the sidebar menu.")
    with c_b:
        if st.button("🔄 Force Cloud Sync"):
            with st.spinner("Syncing..."):
                perform_login_sync()
            st.success("Sync Complete!")

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
    
    # SETUP
    subs_raw = get_teacher_subjects_full(st.session_state.user[0])
    subjects = [s[1] for s in subs_raw]
    if not subjects: st.warning("Please add subjects in Dashboard first."); return
    
    school_years = get_school_years()
    
    with st.expander("⚙️ Class Selection", expanded=True):
        c1,c2,c3,c4,c5 = st.columns(5)
        yr = c1.selectbox("Year", school_years, index=1) # Default to current year
        subj = c2.selectbox("Subject", subjects)
        q = c3.selectbox("Quarter", ["Q1","Q2","Q3","Q4"])
        lvl = c4.selectbox("Level", ["M1","M2","M3","M4","M5","M6"])
        rm = c5.selectbox("Room", [str(i) for i in range(1,16)])
    
    roster = get_class_roster(lvl, rm, only_active=True)
    if roster.empty: st.warning("No Active students in this class."); return

    # TABS FOR TESTS
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
        
        # --- DYNAMIC TASK SELECTOR ---
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
                edited_df = st.data_editor(
                    df_editor, 
                    hide_index=True, 
                    column_config=col_config, 
                    width="stretch", 
                    height=500,
                    disabled=["Weighted", "Total Raw"]
                )
                if st.form_submit_button("💾 Save All Changes", type="primary"):
                    with st.spinner("Saving..."):
                        ok, msg = save_batch_tasks_and_grades(subj, q, yr, test_name, edited_df, total_test_max, weight, st.session_state.user[0])
                        if ok: st.success(msg); time.sleep(0.5); st.rerun()

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
                    edited_df = st.data_editor(df_editor, hide_index=True, column_config=col_config, width="stretch", height=500)
                    if st.form_submit_button(f"💾 Save {task_choice}", type="primary"):
                        with st.spinner("Saving..."):
                            ok = update_specific_task_column(subj, q, yr, test_name, task_choice, edited_df, st.session_state.user[0], total_test_max, weight)
                            if ok: st.success("Saved!"); time.sleep(0.5); st.rerun()

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
            if st.form_submit_button("💾 Save Final Scores", type="primary"):
                 with st.spinner("Saving..."):
                    ok = save_final_exam_batch(subj, q, yr, edited_final, max_final, st.session_state.user[0])
                    if ok: st.success("Saved!"); time.sleep(0.5); st.rerun()

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
                if ok: st.success(msg); time.sleep(1.5); st.rerun()
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

def page_student_record_teacher_view():
    st.title("👤 Student Record & Academic History")

    # --- 1. PREPARE DATA ---
    # Fetch all students (Active only)
    all_students = fetch_all_records("Students")
    roster = pd.DataFrame(all_students)
    if not roster.empty:
        roster = roster[roster['status'] == 'Active']
    
    if roster.empty:
        st.warning("No active students found in the system.")
        return

    # Helper: Custom Semester GPA Scale
    def get_sem_gpa(score):
        if score >= 80: return 4.0
        elif score >= 75: return 3.5
        elif score >= 70: return 3.0
        elif score >= 65: return 2.5
        elif score >= 60: return 2.0
        elif score >= 55: return 1.5
        elif score >= 50: return 1.0
        else: return 0.0

    # --- 2. SEARCH LOGIC (Auto-Clear) ---
    # Initialize session state to hold the selected student view
    if 'sr_view_student' not in st.session_state:
        st.session_state.sr_view_student = None # Stores {'id': '...', 'name': '...'}

    def perform_search():
        query = st.session_state.sr_search_input.strip().lower()
        if not query: return
        
        # Search by ID (Exact)
        match = roster[roster['student_id'].astype(str) == query]
        
        # If no ID match, Search by Name (Contains)
        if match.empty:
            match = roster[roster['student_name'].astype(str).str.lower().str.contains(query)]
        
        if not match.empty:
            # Select the first result found
            found = match.iloc[0]
            st.session_state.sr_view_student = {
                'id': str(found['student_id']),
                'name': found['student_name']
            }
        else:
            st.toast(f"⚠️ Student '{query}' not found.", icon="🚫")
        
        # AUTO DELETE: Clear the input box
        st.session_state.sr_search_input = ""

    # The Search Box
    st.text_input(
        "🔍 Search Student (Type Name or ID and Press Enter)", 
        key="sr_search_input", 
        on_change=perform_search
    )

    # --- 3. DISPLAY RECORD ---
    if st.session_state.sr_view_student:
        s_id = st.session_state.sr_view_student['id']
        s_name = st.session_state.sr_view_student['name']

        # Header
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(f"### 🎓 Academic History: {s_name} ({s_id})")
        with c2:
            if st.button("❌ Close Record"):
                st.session_state.sr_view_student = None
                st.rerun()
        st.markdown("---")
        
        # Fetch Grades
        all_grades = fetch_all_records("Grades")
        
        # --- SECURITY FILTER: Only show grades recorded by THIS teacher ---
        current_teacher = st.session_state.user[0]
        
        student_grades = [
            g for g in all_grades 
            if clean_id(g['student_id']) == s_id and g['recorded_by'] == current_teacher
        ]
        # -----------------------------------------------------------------
        
        if not student_grades:
            st.info(f"No academic records found for {s_name} recorded by you ({current_teacher}).")
            return

        # Process Grades
        df = pd.DataFrame(student_grades)
        
        # Group by School Year
        unique_years = df['school_year'].unique()
        unique_years = sorted(unique_years, reverse=True) 
        
        for yr in unique_years:
            st.markdown(f"#### 📅 School Year: {yr}")
            
            year_data = df[df['school_year'] == yr]
            subjects = year_data['subject'].unique()
            
            academic_table = []
            
            for sub in subjects:
                sub_grades = year_data[year_data['subject'] == sub]
                teacher = sub_grades.iloc[0]['recorded_by'] if not sub_grades.empty else "Unknown"
                
                # Get Quarter Scores
                def get_q_score(q_name):
                    q_row = sub_grades[sub_grades['quarter'] == q_name]
                    if not q_row.empty:
                        return float(q_row.iloc[0]['total_score'])
                    return 0.0

                q1 = get_q_score("Q1")
                q2 = get_q_score("Q2")
                q3 = get_q_score("Q3")
                q4 = get_q_score("Q4")
                
                # Calculate Semesters
                sem1_total = q1 + q2
                sem1_gpa = get_sem_gpa(sem1_total)
                
                sem2_total = q3 + q4
                sem2_gpa = get_sem_gpa(sem2_total)
                
                academic_table.append({
                    "Subject": sub,
                    "Teacher": teacher,
                    "Q1": fmt_score(q1),
                    "Q2": fmt_score(q2),
                    "1st Sem": fmt_score(sem1_total),
                    "GPA 1": f"{sem1_gpa:.1f}",
                    "Q3": fmt_score(q3),
                    "Q4": fmt_score(q4),
                    "2nd Sem": fmt_score(sem2_total),
                    "GPA 2": f"{sem2_gpa:.1f}"
                })
            
            # Display Table
            if academic_table:
                df_display = pd.DataFrame(academic_table)
                st.dataframe(
                    df_display, 
                    hide_index=True, 
                    use_container_width=True,
                    column_config={
                        "Subject": st.column_config.TextColumn("Subject", width="small"),
                        "Teacher": st.column_config.TextColumn("Teacher", width="small"),
                        "Q1": st.column_config.TextColumn("Q1", width="small"),
                        "Q2": st.column_config.TextColumn("Q2", width="small"),
                        "1st Sem": st.column_config.TextColumn("Sem 1 Total", width="small", help="Q1 + Q2"),
                        "GPA 1": st.column_config.TextColumn("Sem 1 GPA", width="small"),
                        "Q3": st.column_config.TextColumn("Q3", width="small"),
                        "Q4": st.column_config.TextColumn("Q4", width="small"),
                        "2nd Sem": st.column_config.TextColumn("Sem 2 Total", width="small", help="Q3 + Q4"),
                        "GPA 2": st.column_config.TextColumn("Sem 2 GPA", width="small"),
                    }
                )
            else:
                st.caption("No subjects found for this year.")
            
            st.divider()

def page_attendance():
    st.title("📋 Class Attendance")
    
    # 1. Select Subject & Class
    user = st.session_state.user[0]
    subs_raw = get_teacher_subjects_full(user)
    subjects = [s[1] for s in subs_raw]
    
    if not subjects:
        st.warning("No subjects assigned.")
        return

    c1, c2, c3, c4 = st.columns(4)
    subject = c1.selectbox("Subject", subjects)
    level = c2.selectbox("Level", ["M1","M2","M3","M4","M5","M6"])
    room = c3.selectbox("Room", [str(i) for i in range(1,16)])
    date_sel = c4.date_input("Date", datetime.date.today())
    
    # 2. Get Roster
    roster = get_class_roster(level, room, only_active=True)
    if roster.empty:
        st.info("No students found in this class.")
        return
        
    # 3. Fetch Existing Attendance for this specific day/subject
    date_str = str(date_sel)
    all_att = fetch_all_records("Attendance")
    
    # Create a dictionary of existing status: {student_id: status}
    existing_map = {}
    for r in all_att:
        if (str(r.get('subject')) == subject and 
            str(r.get('date')) == date_str):
            existing_map[clean_id(r['student_id'])] = r['status']
            
    # 4. Prepare Data for Editor
    # Allowed statuses
    status_options = [
        "Present", "Sick Leave", "Excuse", "Personal Leave", 
        "Absent", "Skip", "Activity", "Late"
    ]
    
    editor_data = []
    # Sort roster by class number just in case
    roster['class_no'] = pd.to_numeric(roster['class_no'], errors='coerce')
    roster = roster.sort_values('class_no')

    for idx, row in roster.iterrows():
        sid = str(row['student_id'])
        current_status = existing_map.get(sid, "Present") # Default to Present
        
        editor_data.append({
            "No.": row['class_no'],  # <--- NEW COLUMN ADDED
            "Student ID": sid,
            "Name": row['student_name'],
            "Status": current_status
        })
        
    df_editor = pd.DataFrame(editor_data)
    
    # 5. Show Data Editor
    st.subheader(f"Date: {date_str}")
    
    edited_df = st.data_editor(
        df_editor,
        column_config={
            "No.": st.column_config.NumberColumn("No.", disabled=True, width="small"),
            "Student ID": st.column_config.TextColumn("ID", disabled=True, width="medium"),
            "Name": st.column_config.TextColumn("Name", disabled=True, width="large"),
            "Status": st.column_config.SelectboxColumn(
                "Status",
                options=status_options,
                required=True,
                width="medium"
            )
        },
        hide_index=True,
        use_container_width=True,
        height=500
    )
    
    # 6. Save Button
    if st.button("💾 Save Attendance", type="primary"):
        new_records = []
        
        # Filter out existing records for this day/subject to replace them
        other_att = [
            r for r in all_att 
            if not (str(r.get('subject')) == subject and str(r.get('date')) == date_str and str(r.get('student_id')) in df_editor['Student ID'].values)
        ]
        
        # Build new rows
        timestamp = str(datetime.datetime.now())
        for index, row in edited_df.iterrows():
            uid = f"{row['Student ID']}_{subject}_{date_str}"
            new_records.append({
                "uid": uid,
                "student_id": row['Student ID'],
                "student_name": row['Name'],
                "subject": subject,
                "date": date_str,
                "status": row['Status'],
                "recorded_by": user,
                "timestamp": timestamp
            })
            
        # Combine and Save
        final_list = other_att + new_records
        overwrite_sheet_data("Attendance", final_list)
        st.success("✅ Attendance Saved Successfully!")
        time.sleep(1)
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
        if sel == "📜 My Grades": page_student_portal_grades()
        elif sel == "⚙️ Settings": page_student_settings()