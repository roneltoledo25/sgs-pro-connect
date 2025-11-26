import streamlit as st
import sqlite3
import pandas as pd
import io
import time
import datetime
from PIL import Image

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="SGS Pro Connect | Admin",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STUNNING PROFESSIONAL CSS (Dark/Light Mode Compatible) ---
st.markdown("""
<style>
    /* Global Styles */
    .main {
        padding-top: 2rem;
    }
    
    /* Typography & Headers */
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
    
    /* Beautiful Gradient Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #2b5876 0%, #4e4376 100%);
        color: white !important;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        letter-spacing: 0.5px;
        padding: 0.6rem 1.2rem;
        transition: all 0.3s ease;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        opacity: 0.95;
    }
    
    .stButton > button:active {
        transform: translateY(0);
    }

    /* Input Fields Polish */
    .stTextInput > div > div > input, .stSelectbox > div > div > div {
        border-radius: 8px;
    }
    
    /* Table/Dataframe Styling */
    [data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid rgba(128, 128, 128, 0.1);
    }
    
    /* Sidebar Profile Image */
    .profile-pic { 
        border-radius: 50%; 
        border: 3px solid var(--primary-color);
        padding: 3px;
    }
    
    /* Expander Styling */
    .streamlit-expanderHeader {
        font-weight: 600;
        background-color: var(--secondary-background-color);
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTS ---
DB_NAME = "sgs_pro_final_v12.db" # Database V12
SCHOOL_CODE = "SK2025"

# --- HELPER: GENERATE SCHOOL YEARS ---
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

# --- DATABASE MANAGEMENT ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Teachers/Admin Table
    c.execute("""CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, profile_pic BLOB)""")
    
    # Create Default Admin if not exists
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('admin', 'admin123', 'Admin'))
    
    # Subjects Table
    c.execute("""CREATE TABLE IF NOT EXISTS subjects (id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_username TEXT, subject_name TEXT, UNIQUE(teacher_username, subject_name))""")
    
    # Students Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            student_name TEXT,
            class_no INTEGER,
            grade_level TEXT,
            room TEXT,
            photo BLOB,
            password TEXT
        )
    """)
    
    try: c.execute("ALTER TABLE students ADD COLUMN password TEXT")
    except: pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            subject TEXT,
            quarter TEXT,
            school_year TEXT,
            test1 REAL, test2 REAL, test3 REAL, final_score REAL,
            total_score REAL,
            recorded_by TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, subject, quarter, school_year)
        )
    """)
    conn.commit()
    conn.close()

# --- BACKEND FUNCTIONS ---

def login_staff(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    return c.fetchone()

def login_student(student_id, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT student_id, student_name, password, photo FROM students WHERE student_id = ?", (student_id,))
    data = c.fetchone()
    conn.close()
    
    if data:
        db_pass = data[2]
        if not db_pass:
            if str(password) == str(student_id): return data
        elif str(password) == str(db_pass):
            return data
    return None

def change_student_password(s_id, new_pass):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("UPDATE students SET password = ? WHERE student_id = ?", (new_pass, s_id))
    conn.commit()
    conn.close()

def register_user(username, password, code):
    if code != SCHOOL_CODE: return False, "❌ Invalid School Code!"
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, 'Teacher'))
        conn.commit()
        return True, "✅ Success"
    except: return False, "⚠️ Username taken"

# --- ADMIN FUNCTIONS ---
def get_admin_stats():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE role='Teacher'")
    t_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM students")
    s_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM subjects")
    sub_count = c.fetchone()[0]
    conn.close()
    return t_count, s_count, sub_count

def get_all_teachers_with_counts():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("""
        SELECT u.username, u.password, COUNT(s.id) as subject_count 
        FROM users u 
        LEFT JOIN subjects s ON u.username = s.teacher_username 
        WHERE u.role = 'Teacher' 
        GROUP BY u.username
    """, conn)
    conn.close()
    return df

def delete_teacher(username):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.execute("DELETE FROM subjects WHERE teacher_username = ?", (username,))
    conn.commit()
    conn.close()

def admin_reset_teacher_password(username, new_pass):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("UPDATE users SET password = ? WHERE username = ?", (new_pass, username))
    conn.commit()
    conn.close()

def get_all_students_admin():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT student_id, student_name, grade_level, room, password FROM students", conn)
    conn.close()
    return df

def delete_student_admin(s_id):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM students WHERE student_id = ?", (s_id,))
    conn.execute("DELETE FROM grades WHERE student_id = ?", (s_id,))
    conn.commit()
    conn.close()

def admin_reset_student_password(s_id, new_pass):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("UPDATE students SET password = ? WHERE student_id = ?", (new_pass, s_id))
    conn.commit()
    conn.close()

# --- EXISTING FUNCTIONS (Unchanged) ---
def update_teacher_pic(username, image_bytes):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("UPDATE users SET profile_pic = ? WHERE username = ?", (sqlite3.Binary(image_bytes), username))
    conn.commit()
    conn.close()

def update_student_pic(student_id, image_bytes):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("UPDATE students SET photo = ? WHERE student_id = ?", (sqlite3.Binary(image_bytes), student_id))
    conn.commit()
    conn.close()

def get_teacher_data(username):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT profile_pic FROM users WHERE username = ?", (username,))
    data = c.fetchone()
    conn.close()
    return data[0] if data else None

def get_student_photo(student_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT photo FROM students WHERE student_id = ?", (student_id,))
    data = c.fetchone()
    conn.close()
    return data[0] if data else None

def get_student_details(student_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT student_name, grade_level, room, photo FROM students WHERE student_id = ?", (student_id,))
    data = c.fetchone()
    conn.close()
    return data

def get_next_class_no(level, room):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT MAX(class_no) FROM students WHERE grade_level = ? AND room = ?", (level, room))
    val = c.fetchone()[0]
    conn.close()
    return 1 if val is None else val + 1

def add_single_student(s_id, name, no, level, room):
    conn = sqlite3.connect(DB_NAME)
    try:
        s_id = str(s_id).split('.')[0]
        conn.execute("""
            INSERT INTO students (student_id, student_name, class_no, grade_level, room)
            VALUES (?, ?, ?, ?, ?)
        """, (s_id, name, no, level, room))
        conn.commit()
        conn.close()
        return True, f"✅ Added {name} (No. {no})"
    except sqlite3.IntegrityError:
        conn.close()
        return False, f"⚠️ Student ID {s_id} already exists!"

def update_student_details(s_id, new_name, new_no):
    conn = sqlite3.connect(DB_NAME)
    try:
        conn.execute("UPDATE students SET student_name = ?, class_no = ? WHERE student_id = ?", (new_name, new_no, s_id))
        conn.commit()
        conn.close()
        return True, "✅ Updated Successfully"
    except Exception as e:
        conn.close()
        return False, str(e)

def delete_single_student(s_id):
    conn = sqlite3.connect(DB_NAME)
    try:
        conn.execute("DELETE FROM students WHERE student_id = ?", (s_id,))
        conn.commit()
        return True, "Deleted"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def delete_entire_roster(level, room):
    conn = sqlite3.connect(DB_NAME)
    try:
        conn.execute("DELETE FROM students WHERE grade_level = ? AND room = ?", (level, room))
        conn.commit()
        return True, "Class Cleared"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def upload_roster(df, level, room):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    added_count = 0
    errors = []
    
    for index, row in df.iterrows():
        try:
            s_id = str(row['ID']).strip()
            if s_id.endswith('.0'): s_id = s_id[:-2]
            name = str(row['Name']).strip()
            no = int(row['No'])
            c.execute("INSERT INTO students (student_id, student_name, class_no, grade_level, room) VALUES (?, ?, ?, ?, ?)", 
                      (s_id, name, no, level, room))
            added_count += 1
        except sqlite3.IntegrityError:
            errors.append(f"ID {s_id} skipped (Duplicate)")
        except:
            errors.append(f"Error on row {index}")
            
    conn.commit()
    conn.close()
    return True, f"✅ Uploaded {added_count} students.", errors

def get_class_roster(level, room):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM students WHERE grade_level = ? AND room = ? ORDER BY class_no ASC", conn, params=(level, room))
    conn.close()
    if not df.empty:
        df['student_id'] = df['student_id'].astype(str).str.replace(r'\.0$', '', regex=True)
    return df

def get_teacher_subjects_full(teacher):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, subject_name FROM subjects WHERE teacher_username = ?", (teacher,))
    return c.fetchall()

def add_subject(teacher, subject):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT teacher_username FROM subjects WHERE subject_name = ?", (subject,))
    existing = c.fetchone()
    if existing:
        conn.close()
        return False, f"⚠️ Conflict: '{subject}' is already owned by Teacher {existing[0]}."
    try:
        c.execute("INSERT INTO subjects (teacher_username, subject_name) VALUES (?, ?)", (teacher, subject))
        conn.commit()
        conn.close()
        return True, "Added"
    except: 
        conn.close()
        return False, "Error adding subject"

def delete_subject(sub_id):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM subjects WHERE id = ?", (sub_id,))
    conn.commit()
    conn.close()

def update_subject(sub_id, new_name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id FROM subjects WHERE subject_name = ? AND id != ?", (new_name, sub_id))
    if c.fetchone():
        conn.close()
        return False 
    try:
        c.execute("UPDATE subjects SET subject_name = ? WHERE id = ?", (new_name, sub_id))
        conn.commit()
        conn.close()
        return True
    except: 
        conn.close()
        return False

def get_grade_record(student_id, subject, quarter, year):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT test1, test2, test3, final_score, total_score 
        FROM grades 
        WHERE student_id = ? AND subject = ? AND quarter = ? AND school_year = ?
    """, (student_id, subject, quarter, year))
    data = c.fetchone()
    conn.close()
    return data

def save_grade(data):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM grades WHERE student_id = ? AND subject = ? AND quarter = ? AND school_year = ?", 
                  (data['s_id'], data['subj'], data['q'], data['year']))
        
        c.execute("""
            INSERT INTO grades (student_id, subject, quarter, school_year, test1, test2, test3, final_score, total_score, recorded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (data['s_id'], data['subj'], data['q'], data['year'], 
              data['t1'], data['t2'], data['t3'], data['final'], data['total'], data['teacher']))
        
        conn.commit()
        return True, "Saved Successfully"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def get_student_full_report(student_id):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("""
        SELECT school_year, quarter, subject, total_score 
        FROM grades 
        WHERE student_id = ?
        ORDER BY school_year DESC, subject ASC, quarter ASC
    """, conn, params=(student_id,))
    conn.close()
    return df

# --- UI COMPONENTS ---

def login_screen():
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        st.markdown("## SGS Pro Connect")
        # --- MODIFIED LOGO PATH AS REQUESTED ---
        st.image("logo/images.jpeg", width=300)
        # ---------------------------------------
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
                            st.session_state.role = user[2] # 'Teacher' or 'Admin'
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
                    else: st.error("Invalid ID or Password")

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
            pic = get_teacher_data(username)
            if pic: st.image(Image.open(io.BytesIO(pic)), width=120)
            else: st.image("https://cdn-icons-png.flaticon.com/512/1995/1995539.png", width=120)
            
            with st.expander("📷 Photo"):
                up = st.file_uploader("Up", type=['jpg','png'], label_visibility="collapsed")
                if up: 
                    update_teacher_pic(username, up.getvalue())
                    st.rerun()
            
            st.markdown("---")
            menu = st.radio("Menu", ["Dashboard", "📂 Student Roster", "📝 Input Grades", "📊 Gradebook", "👤 Student Record"])
            
        else: # Student
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

def get_student_grades_for_teacher_view(student_id, teacher_username):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("""
        SELECT school_year, quarter, subject, total_score 
        FROM grades 
        WHERE student_id = ? AND recorded_by = ?
        ORDER BY school_year DESC, subject ASC, quarter ASC
    """, conn, params=(student_id, teacher_username))
    conn.close()
    return df

# --- ADMIN PAGES ---
def page_admin_dashboard():
    st.title("🛡️ Admin Dashboard")
    t, s, sub = get_admin_stats()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Teachers", t)
    c2.metric("Total Students", s)
    c3.metric("Total Subjects", sub)
    
    st.markdown("---")
    st.info("Select 'Manage Teachers' or 'Manage Students' from the sidebar to edit accounts.")

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
                        st.warning("Deleted!")
                        time.sleep(1)
                        st.rerun()
    else:
        st.warning("No teachers found.")

def page_admin_manage_students():
    st.title("🎓 Manage Students")
    df = get_all_students_admin()
    
    search = st.text_input("🔍 Search Student ID or Name")
    if search:
        df = df[df['student_name'].str.contains(search, case=False) | df['student_id'].str.contains(search)]
    
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
            st.warning(f"Student {target_id} deleted.")
            time.sleep(1)
            st.rerun()

# --- TEACHER PAGES ---
def page_dashboard():
    st.title("📊 Teacher Dashboard")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM students")
    total_students = c.fetchone()[0]
    conn.close()
    
    col_main_1, col_main_2 = st.columns(2)
    col_main_1.metric("Total Students", total_students)
    col_main_2.metric("Active Year", get_school_years()[0])
    
    st.markdown("---")
    st.subheader("📚 Subject Management")
    
    with st.expander("➕ Add New Subject"):
        with st.form("add_sub_form"):
            new_s = st.text_input("Subject Name (e.g., Mathematics)")
            st.caption("Note: Subject names must be unique.")
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
                        else: st.error("Name taken!")
                if c4.button("🗑️", key=f"del_{sub_id}"):
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
    t1, t2, t3, t4 = st.tabs(["📤 Bulk Upload", "➕ Manual Add", "✏️ Edit / Delete", "🗑️ Reset Class"])
    
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
                    if errs: st.error(f"{len(errs)} Errors")
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
        roster = get_class_roster(level, room)
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
        st.error("⚠️ DANGER ZONE")
        if st.button(f"Delete ALL in {level}/{room}"):
            delete_entire_roster(level, room); st.rerun()
            
    curr = get_class_roster(level, room)
    if not curr.empty:
        curr['student_id'] = curr['student_id'].astype(str)
        st.dataframe(curr[['class_no','student_id','student_name']], hide_index=True, width="stretch")

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

    roster = get_class_roster(lvl, rm)
    if roster.empty: st.warning("No students."); return

    conn = sqlite3.connect(DB_NAME)
    graded_ids = pd.read_sql_query("SELECT student_id FROM grades WHERE subject=? AND quarter=? AND school_year=?", conn, params=(subj, q, yr))['student_id'].astype(str).tolist()
    conn.close()

    total_students = len(roster)
    roster_ids = roster['student_id'].astype(str).str.replace(r'\.0$', '', regex=True).tolist()
    done_count = len(set(graded_ids).intersection(roster_ids))
    prog_val = done_count / total_students if total_students > 0 else 0
    st.progress(prog_val, text=f"📊 Class Progress: {done_count} / {total_students} Finished")

    roster['student_id_clean'] = roster['student_id'].astype(str).str.replace(r'\.0$', '', regex=True)
    roster['lbl'] = roster.apply(lambda x: f"{x['class_no']}. {x['student_name']} ({'✅' if x['student_id_clean'] in graded_ids else '❌'})", axis=1)
    sel_lbl = st.selectbox("Choose:", roster['lbl'])
    sel_row = roster[roster['lbl'] == sel_lbl].iloc[0]
    s_id, s_name = sel_row['student_id_clean'], sel_row['student_name']

    st.markdown("---")
    left, right = st.columns([1, 2.5])
    with left:
        st.markdown(f"**{s_name}**")
        photo_blob = get_student_photo(s_id)
        if photo_blob: st.image(Image.open(io.BytesIO(photo_blob)), width=150)
        else: st.image("https://cdn-icons-png.flaticon.com/512/3237/3237472.png", width=150)
        with st.popover("📷 Upload Photo"):
            stu_pic = st.file_uploader("Upload", type=['jpg','png'], key="stu_up")
            if stu_pic:
                update_student_pic(s_id, stu_pic.getvalue())
                st.rerun()

    with right:
        ex = get_grade_record(s_id, subj, q, yr)
        is_locked = False
        if ex:
            is_locked = True
            if st.checkbox("🔓 Unlock to Edit", value=False): is_locked = False
            if is_locked: st.info("🔒 Grades locked.")

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
    
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query(f"""
        SELECT s.class_no, s.student_id, s.student_name, 
        g.test1, g.test2, g.test3, g.final_score, g.total_score
        FROM students s LEFT JOIN grades g 
        ON s.student_id = g.student_id AND g.subject='{s}' AND g.quarter='{q}'
        WHERE s.grade_level='{l}' AND s.room='{r}' ORDER BY s.class_no
    """, conn)
    conn.close()
    
    if not df.empty: df['student_id'] = df['student_id'].astype(str).str.replace(r'\.0$', '', regex=True)
    st.dataframe(df.style.format(precision=1), width="stretch")
    if not df.empty:
        st.download_button("⬇️ Excel", df.to_csv(index=False), f"gradebook_{s}_{q}.csv", "text/csv")

def page_student_record_teacher_view():
    st.title("👤 Student Individual Record")
    st.markdown("Search for a student to view their academic summary in **your subjects only**.")
    s_search = st.text_input("Enter Student ID", placeholder="e.g., 10101")
    if s_search:
        s_search = str(s_search).strip()
        details = get_student_details(s_search)
        if details:
            name, lvl, rm, photo = details
            c_info, c_table = st.columns([1, 3])
            with c_info:
                if photo: st.image(Image.open(io.BytesIO(photo)), width=180)
                else: st.image("https://cdn-icons-png.flaticon.com/512/3237/3237472.png", width=180)
                st.markdown(f"### {name}"); st.caption(f"ID: {s_search}"); st.info(f"Class: {lvl} / {rm}")
            with c_table:
                # Use teacher-specific view
                df = get_student_grades_for_teacher_view(s_search, st.session_state.user[0])
                if not df.empty:
                    display_academic_transcript(df)
                else: st.warning("No grades recorded by you.")
        else: st.error("Not found.")

# --- STUDENT PORTAL PAGES ---

def display_academic_transcript(df):
    """Helper to display the pivot table and semester calculation"""
    pivot = df.pivot_table(index=['school_year', 'subject'], columns='quarter', values='total_score', aggfunc='first').reset_index()
    for q in ['Q1', 'Q2', 'Q3', 'Q4']:
        if q not in pivot.columns: pivot[q] = 0.0
    
    pivot['Sem 1'] = pivot['Q1'].fillna(0) + pivot['Q2'].fillna(0)
    pivot['Sem 2'] = pivot['Q3'].fillna(0) + pivot['Q4'].fillna(0)
    pivot['GPA S1'] = pivot['Sem 1'].apply(get_grade_point)
    pivot['GPA S2'] = pivot['Sem 2'].apply(get_grade_point)

    unique_years = pivot['school_year'].unique()
    for yr in unique_years:
        st.markdown(f"#### 🗓️ Academic Year: {yr}")
        yr_data = pivot[pivot['school_year'] == yr].copy()
        
        display_df = yr_data[['subject', 'Q1', 'Q2', 'Sem 1', 'GPA S1', 'Q3', 'Q4', 'Sem 2', 'GPA S2']].copy()
        
        # Renamed columns to avoid duplicate 'Grade' names
        display_df.columns = ['Subject', 'Q1 (50)', 'Q2 (50)', 'Sem 1 Total', 'S1 Grade', 'Q3 (50)', 'Q4 (50)', 'Sem 2 Total', 'S2 Grade']
        
        st.dataframe(display_df.style.format(precision=1), hide_index=True, width="stretch")
        
        with st.expander("ℹ️ Grading Scale Reference"):
            st.markdown("""
            | Score | Grade | | Score | Grade |
            |---|---|---|---|---|
            | 80-100 | **4.0** | | 60-64 | **2.0** |
            | 75-79 | **3.5** | | 55-59 | **1.5** |
            | 70-74 | **3.0** | | 50-54 | **1.0** |
            | 65-69 | **2.5** | | 0-49 | **0.0** |
            """)

def page_student_portal_grades():
    s_data = st.session_state.user
    s_id = s_data[0] # Tuple: id, name, pass, photo
    
    st.title("📜 My Academic Record")
    st.info(f"Welcome, {s_data[1]}. Here is your complete academic history across all subjects.")
    
    df = get_student_full_report(s_id)
    if not df.empty:
        display_academic_transcript(df)
    else:
        st.warning("No grades found for your ID yet.")

def page_student_settings():
    st.title("⚙️ Student Settings")
    st.markdown("### 🔐 Change Password")
    st.caption("Change your password from your ID to something private.")
    
    with st.form("pwd_change"):
        p1 = st.text_input("New Password", type="password")
        p2 = st.text_input("Confirm New Password", type="password")
        
        if st.form_submit_button("Update Password"):
            if p1 and p2:
                if p1 == p2:
                    change_student_password(st.session_state.user[0], p1)
                    st.success("✅ Password updated! Please log out and log in again.")
                else:
                    st.error("⚠️ Passwords do not match.")
            else:
                st.warning("Please fill both fields.")

# --- MAIN ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    init_db()

if not st.session_state.logged_in:
    login_screen()
else:
    sel = sidebar_menu()
    
    # ROUTING BASED ON ROLE
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