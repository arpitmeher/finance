import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    temp = db.execute("SELECT symbol FROM purchased WHERE user_id = ?", session["user_id"])
    myset = set()
    for name in temp:
        myset.add(name["symbol"])

    total = 0
    table = []
    for symbol in myset:
        bought = db.execute("SELECT SUM(shares) FROM purchased WHERE symbol = ? AND action = ?", symbol, "BUY")
        sold = db.execute("SELECT SUM(shares) FROM purchased WHERE symbol = ? AND action = ?", symbol, "SELL")

        if type(sold[0]["SUM(shares)"]) == int:
            current_shares = bought[0]["SUM(shares)"] - sold[0]["SUM(shares)"]
        else:
            current_shares = bought[0]["SUM(shares)"]

        if current_shares > 0:
            company = lookup(symbol)
            table.append({
                "Symbol": symbol,
                "Name": company["name"],
                "Shares": current_shares,
                "Price": company["price"],
                "Total": current_shares * company["price"]
            })

            total += current_shares * company["price"]
    total += balance[0]["cash"]

    return render_template("index.html", table=table, cash=balance[0]["cash"], total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("Input is blank")
        elif lookup(request.form.get("symbol")) == None:
            return apology("Symbol does not exist")
        try:
            shares = int(request.form.get("shares"))
            if shares < 1:
                return apology("invalid number of shares")
        except ValueError:
            return apology("invalid number of shares")

        temp = lookup(request.form.get("symbol"))
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        user_id = session["user_id"]

        balance = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cost = shares * temp["price"]

        if balance[0]["cash"] < cost:
            return apology("Not enough CASH to complete the purchase")

        new_balance = balance[0]["cash"] - cost

        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_balance, user_id)
        db.execute("INSERT INTO purchased (user_id, symbol, company, shares, price, time, action) VALUES(?, ?, ?, ?, ?, ?, ?)",
                   user_id, temp["symbol"], temp["name"], shares, temp["price"], now, "BUY")

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    transactions = db.execute("SELECT symbol, shares, price, time, action FROM purchased WHERE user_id = ?", session["user_id"])

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    INDEX_MSG = "Logged Out successfully"
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        quotes = lookup(request.form.get("symbol"))
        if quotes is None:
            return apology("invalid symbol", 400)
        else:
            return render_template("quoted.html", quotes=quotes)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("two passwords doesn't match", 400)

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        if len(rows) != 0:
            return apology("Username already exist", 400)

        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get(
                   "username"), generate_password_hash(request.form.get("password")))

        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    temp1 = db.execute("SELECT symbol FROM purchased WHERE user_id = ?", session["user_id"])
    myset = set()
    for name in temp1:
        myset.add(name["symbol"])

    if request.method == "POST":

        try:
            shares = int(request.form.get("shares"))
            if shares < 1:
                return apology("invalid number of shares")
        except ValueError:
            return apology("invalid number of shares")

        symbol = request.form.get("symbol")
        if symbol not in myset:
            return apology("invalid SYMBOL")

        bought = db.execute("SELECT SUM(shares) FROM purchased WHERE symbol = ? AND action = ?", symbol, "BUY")
        sold = db.execute("SELECT SUM(shares) FROM purchased WHERE symbol = ? AND action = ?", symbol, "SELL")

        if type(sold[0]["SUM(shares)"]) == int:
            current_shares = bought[0]["SUM(shares)"] - sold[0]["SUM(shares)"]
        else:
            current_shares = bought[0]["SUM(shares)"]

        temp = lookup(symbol)
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        user_id = session["user_id"]

        balance = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cost = shares * temp["price"]

        new_balance = balance[0]["cash"] + cost

        if current_shares < shares:
            return apology("invalid number of shares")
        else:

            db.execute("UPDATE users SET cash = ? WHERE id = ?", new_balance, user_id)
            db.execute("INSERT INTO purchased (user_id, symbol, company, shares, price, time, action) VALUES(?, ?, ?, ?, ?, ?, ?)",
                       user_id, temp["symbol"], temp["name"], shares, temp["price"], now, "SELL")

        return redirect("/")

    else:
        return render_template("sell.html", myset=myset)


@app.route("/change", methods=["POST", "GET"])
@login_required
def change():

    if request.method == "POST":
        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Ensure new password was submitted
        if not request.form.get("new_password"):
            return apology("must provide new password", 400)

        elif request.form.get("con_new_password") != request.form.get("new_password"):
            return apology("two passwords doesn't match", 400)

        db.execute("UPDATE users SET hash = ? WHERE id = ?", generate_password_hash(request.form.get("new_password")),
                   session["user_id"])

        return redirect("/")

    else:
        return render_template("change.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
