
from flask import Flask, render_template, redirect

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def home():
    if __import__("flask").request.method == "POST":
        return redirect("/role-selection")

    return render_template("login.html")


@app.route("/role-selection")
def role_selection():
    return render_template("role_selection.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


if __name__ == "__main__":
    app.run(debug=True)
