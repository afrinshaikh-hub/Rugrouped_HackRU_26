
from flask import Flask, render_template, redirect, request, session, url_for
import sqlite3
import pandas as pd
from werkzeug.security import generate_password_hash

app = Flask(__name__)
app.secret_key = "ru-grouped-demo-key-change-later"


def get_db():
    conn = sqlite3.connect("rugrouped.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        netid = request.form.get("netid", "").strip()

        if not netid:
            return render_template("login.html")

        # Demo login: no real password verification yet.
        session["netid"] = netid
        return redirect("/role-selection")

    return render_template("login.html")


@app.route("/role-selection")
def role_selection():
    return render_template("role_selection.html")


@app.route("/dashboard")
def dashboard():
    netid = session.get("netid")

    if not netid:
        return redirect("/")

    conn = get_db()
    courses = conn.execute(
        """
        SELECT c.code, c.title, c.professor, c.section
        FROM courses c
        JOIN enrollments e ON e.course_code = c.code
        WHERE e.netid = ?
        ORDER BY c.title
        """,
        (netid,)
    ).fetchall()
    conn.close()

    return render_template("dashboard.html", courses=courses)


@app.route("/leave-course", methods=["POST"])
def leave_course():
    netid = session.get("netid")

    if not netid:
        return redirect("/")

    course_code = request.form.get("course_code", "").strip()

    conn = get_db()
    conn.execute(
        "DELETE FROM enrollments WHERE netid = ? AND course_code = ?",
        (netid, course_code)
    )
    conn.commit()
    conn.close()

    return redirect("/dashboard")



@app.route("/classmates")
def classmates():
    netid = session.get("netid")
    if not netid:
        return redirect("/")

    course_code = request.args.get("course_code", "").strip()
    section = request.args.get("section", "").strip()

    gender = request.args.get("gender", "").strip()
    grad_year = request.args.get("grad_year", "").strip()
    major = request.args.get("major", "").strip()

    conn = get_db()

    course = conn.execute(
        "SELECT * FROM courses WHERE code = ? AND section = ?",
        (course_code, section)
    ).fetchone()

    if not course:
        conn.close()
        return "Course not found.", 404

    # Build filter options from this course's actual roster.
    options = conn.execute(
        """
        SELECT DISTINCT s.gender, s.grad_year, s.major
        FROM students s
        JOIN enrollments e ON e.netid = s.netid
        WHERE e.course_code = ? AND s.netid != ?
        """,
        (course_code, netid)
    ).fetchall()

    genders = sorted({r["gender"] for r in options if r["gender"]})
    years = sorted({r["grad_year"] for r in options if r["grad_year"]})
    majors = sorted({r["major"] for r in options if r["major"]})

    # Every selected filter must match.
    sql = """
        SELECT s.netid, s.first_name, s.last_name, s.gender,
               s.grad_year, s.major, s.bio, e.attendance
        FROM students s
        JOIN enrollments e ON e.netid = s.netid
        WHERE e.course_code = ? AND s.netid != ?
    """
    params = [course_code, netid]

    if gender:
        sql += " AND s.gender = ?"
        params.append(gender)

    if grad_year:
        sql += " AND s.grad_year = ?"
        params.append(int(grad_year))

    if major:
        sql += " AND s.major = ?"
        params.append(major)

    sql += " ORDER BY s.last_name, s.first_name"

    students = conn.execute(sql, params).fetchall()
    conn.close()

    return render_template(
        "classmates.html",
        course=course,
        students=students,
        genders=genders,
        years=years,
        majors=majors,
        selected_gender=gender,
        selected_year=grad_year,
        selected_major=major
    )


@app.route("/profile/<netid>")
def profile(netid):
    current_netid = session.get("netid")
    if not current_netid:
        return redirect("/")

    course_code = request.args.get("course_code", "").strip()
    section = request.args.get("section", "").strip()

    conn = get_db()

    student = conn.execute(
        """
        SELECT s.netid, s.first_name, s.last_name, s.gender,
               s.grad_year, s.major, s.bio
        FROM students s
        JOIN enrollments e ON e.netid = s.netid
        JOIN courses c ON c.code = e.course_code
        WHERE s.netid = ? AND c.code = ? AND c.section = ?
        """,
        (netid, course_code, section)
    ).fetchone()

    course = conn.execute(
        "SELECT * FROM courses WHERE code = ? AND section = ?",
        (course_code, section)
    ).fetchone()

    conn.close()

    if not student or not course:
        return "Student or course not found.", 404

    return render_template(
        "profile.html",
        student=student,
        course=course
    )


@app.route("/send-request", methods=["POST"])
def send_request():
    sender = session.get("netid")

    if not sender:
        return redirect("/")

    receiver = request.form.get("receiver", "").strip()
    course_code = request.form.get("course_code", "").strip()
    message = request.form.get("message", "").strip()

    if not receiver or sender == receiver:
        return "Invalid partner request.", 400

    conn = get_db()

    # Make sure both students belong to this course.
    enrolled = conn.execute(
        """
        SELECT COUNT(*) FROM enrollments
        WHERE course_code = ? AND netid IN (?, ?)
        """,
        (course_code, sender, receiver)
    ).fetchone()[0]

    if enrolled != 2:
        conn.close()
        return "Both students must be enrolled in this course.", 400

    # Avoid sending duplicate pending requests.
    existing = conn.execute(
        """
        SELECT id FROM partner_requests
        WHERE sender = ? AND receiver = ?
          AND course_code = ? AND status = 'pending'
        """,
        (sender, receiver, course_code)
    ).fetchone()

    if existing:
        conn.close()
        return redirect(
            url_for("profile", netid=receiver,
                    course_code=course_code,
                    section=request.form.get("section", ""))
        )


    
   
    conn.execute(
        """
        INSERT INTO partner_requests
            (sender, receiver, course_code, message, status, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        """,
        (sender, receiver, course_code, message, "pending")
    )



    conn.commit()
    conn.close()

    return redirect(
        url_for("profile", netid=receiver,
                course_code=course_code,
                section=request.form.get("section", ""))
    )


@app.route("/instructor", methods=["GET", "POST"])
def instructor():
    if request.method == "GET":
        return render_template("instructor.html")

    course_name = request.form.get("course_name", "").strip()
    course_code = request.form.get("course_code", "").strip()
    professor = request.form.get("professor", "").strip()
    section = request.form.get("section", "").strip()
    roster_file = request.files.get("roster")

    if not all([course_name, course_code, professor, section]):
        return render_template(
            "instructor.html",
            message="Please fill in all course details."
        )

    if not roster_file or not roster_file.filename.lower().endswith(".csv"):
        return render_template(
            "instructor.html",
            message="Please upload a CSV file."
        )

    conn = None

    try:
        df = pd.read_csv(roster_file)
        df.columns = df.columns.str.strip()

        required = {
            "NetID", "Password", "Last_Name", "First_Name",
            "Gender", "Grad_Year", "Major"
        }

        if not required.issubset(df.columns):
            return render_template(
                "instructor.html",
                message="CSV must contain: NetID, Password, Last_Name, "
                        "First_Name, Gender, Grad_Year, Major."
            )

        df = df.dropna(
            subset=["NetID", "First_Name", "Last_Name", "Grad_Year", "Major"]
        ).copy()

        for column in ["NetID", "First_Name", "Last_Name", "Major"]:
            df[column] = df[column].astype(str).str.strip()

        df["NetID"] = df["NetID"].str.lower()

        if df.empty or (df["NetID"] == "").any():
            return render_template(
                "instructor.html",
                message="The roster has no valid student records."
            )

        if df["NetID"].duplicated().any():
            return render_template(
                "instructor.html",
                message="The roster contains duplicate NetIDs."
            )

        df["Grad_Year"] = pd.to_numeric(df["Grad_Year"], errors="raise")
        df["Grad_Year"] = df["Grad_Year"].astype(int)

        conn = get_db()

        existing_course = conn.execute(
            "SELECT code FROM courses WHERE code = ?",
            (course_code,)
        ).fetchone()

        if existing_course:
            conn.execute(
                """
                UPDATE courses
                SET title = ?, professor = ?, section = ?
                WHERE code = ?
                """,
                (course_name, professor, section, course_code)
            )
        else:
            conn.execute(
                """
                INSERT INTO courses (code, title, professor, section)
                VALUES (?, ?, ?, ?)
                """,
                (course_code, course_name, professor, section)
            )

        # Replace enrollments for this course with the uploaded roster.
        conn.execute(
            "DELETE FROM enrollments WHERE course_code = ?",
            (course_code,)
        )

        for _, row in df.iterrows():
            netid = row["NetID"]
            password = str(row["Password"]).strip()

            existing_student = conn.execute(
                "SELECT netid FROM students WHERE netid = ?",
                (netid,)
            ).fetchone()

            if existing_student:
                conn.execute(
                    """
                    UPDATE students
                    SET first_name = ?, last_name = ?, gender = ?,
                        grad_year = ?, major = ?
                    WHERE netid = ?
                    """,
                    (
                        row["First_Name"], row["Last_Name"],
                        str(row["Gender"]).strip(),
                        int(row["Grad_Year"]), row["Major"], netid
                    )
                )
            else:
                conn.execute(
                    """
                    INSERT INTO students
                    (netid, password_hash, first_name, last_name,
                     gender, grad_year, major, bio)
                    VALUES (?, ?, ?, ?, ?, ?, ?, '')
                    """,
                    (
                        netid,
                        generate_password_hash(password or "demo123"),
                        row["First_Name"],
                        row["Last_Name"],
                        str(row["Gender"]).strip(),
                        int(row["Grad_Year"]),
                        row["Major"]
                    )
                )

            conn.execute(
                """
                INSERT INTO enrollments (netid, course_code, attendance)
                VALUES (?, ?, ?)
                """,
                (netid, course_code, 0)
            )

        conn.commit()
        conn.close()

        return render_template(
            "instructor.html",
            message="Roster uploaded successfully! Students can now see this course."
        )

    except Exception:
        if conn is not None:
            conn.rollback()
            conn.close()

        return render_template(
            "instructor.html",
            message="Upload failed. Check the CSV columns and data, then try again."
        )


if __name__ == "__main__":
    app.run(debug=True)
