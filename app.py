"""
Flask application implementing an administration system for KPIs and
organizational structure.  This project was generated from scratch to
address the requirements described by the user: users can authenticate,
edit their KPI results each month, view the KPIs of their direct
reports, manage the KPI catalog, assign KPIs to positions, edit
positions and employees, import new employees from an external
incidencias table and visualise the organisational chart.  The
database schema for this application lives in `kpi_manager_schema.sql`
and must be imported into a MySQL instance prior to running the
application.  The MySQL credentials (root/B1Admin) are used directly in
the connection helper.  Authentication is intentionally kept in
plaintext because this was requested in the requirements.  In a
production environment you should always hash and salt passwords.
"""

from __future__ import annotations

import datetime
import math
"""
This Flask application implements an administration system for KPIs and
organizational structure.  The code has been updated to ensure
compatibility with Python 3.14 and later.  In Python 3.14 the
`pkgutil.get_loader` function was removed, which caused older
versions of Flask to fail during application startup.  To maintain
backwards compatibility, we install a minimal shim for
`pkgutil.get_loader` before importing Flask.  Newer versions of
Flask (>=3.0) no longer rely on this deprecated function, but the
shim ensures that even if an older Flask is installed the app
continues to work.  If you upgrade Flask to a version that
supports Python 3.14 directly this shim will be a no-op.

Do not remove this shim unless you drop support for Python 3.14.
"""

# -----------------------------------------------------------------------------
# Compatibility shim for Python 3.14
#
# In Python 3.14 the `pkgutil.get_loader` function was removed.  Some
# dependencies (notably Flask versions prior to 3.0) still call this
# function indirectly during initialisation.  To avoid runtime errors we
# reintroduce a minimal implementation that proxies to
# `importlib.util.find_spec`, which is the modern approach to find a module's
# loader.  If Flask >= 3.0 is installed this function will not be used, but
# defining it here is harmless.  See:
# https://docs.python.org/3/library/pkgutil.html
import importlib.util
import pkgutil  # type: ignore

if not hasattr(pkgutil, "get_loader"):
    def _get_loader(name: str):
        """Approximate replacement for pkgutil.get_loader using find_spec.

        Returns the loader for the specified module name or None if the
        module cannot be found.  This mirrors the behaviour of the
        original function removed in Python 3.14.
        """
        spec = importlib.util.find_spec(name)
        return spec.loader if spec else None
    # Assign our shim to pkgutil to satisfy consumers expecting get_loader
    pkgutil.get_loader = _get_loader  # type: ignore[attr-defined]

import os
from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)
import pymysql
from pymysql.cursors import DictCursor

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = "please-change-this-secret-key"  # replace with a random value in production

# Load environment variables from .env file if present.  The file should
# define DB_* parameters for the KPI database and INCIDENCIAS_DB_* for
# the external incidencias database.  Using environment variables
# allows you to change credentials without modifying the code.  See
# the README for an example.
load_dotenv()

# Database connection configuration for the KPI system.  Default values
# are provided but can be overridden by environment variables.  If
# DB_PORT is not set, 3306 is used by default.
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "B1Admin"),
    "database": os.getenv("DB_NAME", "kpi_manager"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
    "autocommit": True,
}

# Database configuration for the external incidencias system.  These
# variables are optional; if not provided, the import functionality
# will behave as if there are no external records.  When defined, the
# system will connect to this separate MySQL server to fetch new
# employees.  See the README for details.
INCIDENCIAS_DB_CONFIG = {
    "host": os.getenv("INCIDENCIAS_DB_HOST"),
    "user": os.getenv("INCIDENCIAS_DB_USER"),
    "password": os.getenv("INCIDENCIAS_DB_PASSWORD"),
    "database": os.getenv("INCIDENCIAS_DB_NAME"),
    "port": int(os.getenv("INCIDENCIAS_DB_PORT", "3306")) if os.getenv("INCIDENCIAS_DB_PORT") else 3306,
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
    "autocommit": True,
}

def get_incidencias_connection() -> pymysql.connections.Connection:
    """Return a connection to the external incidencias database.

    If the incidencias configuration is incomplete (e.g., no host or
    database defined), this function will return None.  Callers
    should check for a falsy value before attempting to use the
    connection.
    """
    host = INCIDENCIAS_DB_CONFIG.get("host")
    db = INCIDENCIAS_DB_CONFIG.get("database")
    if not host or not db:
        return None  # external database not configured
    return pymysql.connect(**INCIDENCIAS_DB_CONFIG)


def get_db_connection():
    """Create and return a new database connection.

    Each call returns a fresh connection.  Connections are not pooled to
    keep the implementation straightforward.  Callers are expected to
    close the connection when finished.
    """
    return pymysql.connect(**DB_CONFIG)


def current_period() -> datetime.date:
    """Return a date object representing the first day of the current month.

    This helper is used to determine the period key for KPI results.  KPI
    results are stored per-month (the day-of-month is ignored).  Using
    the first of the month as the canonical date simplifies queries.
    """
    today = datetime.date.today()
    return today.replace(day=1)


# ----------------------------------------------------------------------------
# Authentication routes
# ----------------------------------------------------------------------------

@app.route("/")
def index():
    """Redirect to the appropriate page depending on authentication state."""
    if session.get("user_id"):
        return redirect(url_for("mis_kpis"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """Handle user login.

    Authentication is performed against the `usuarios` table.  The
    passwords are stored in plain text because that is what the user
    requested; do not use this approach in production.  On successful
    login the user id, empleado id and role are stored in the session.
    """
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password:
            flash("Debes ingresar usuario y contraseña", "danger")
            return render_template("login.html")
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, empleado_id, password, rol FROM usuarios WHERE username=%s",
                    (username,),
                )
                user = cur.fetchone()
        finally:
            conn.close()
        if user and password == user["password"]:
            session["user_id"] = user["id"]
            session["empleado_id"] = user["empleado_id"]
            session["rol"] = user["rol"]
            flash("Inicio de sesión exitoso", "success")
            return redirect(url_for("mis_kpis"))
        flash("Usuario o contraseña incorrectos", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    """Clear the session and redirect to the login page."""
    session.clear()
    flash("Sesión cerrada", "info")
    return redirect(url_for("login"))


def require_login(f):
    """Decorator to enforce that the user is authenticated."""
    from functools import wraps

    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapped


# ----------------------------------------------------------------------------
# KPI view and update
# ----------------------------------------------------------------------------

@app.route("/mis_kpis", methods=["GET", "POST"])
@require_login
def mis_kpis():
    """Display and update the KPIs for the current user and their reports.

    On a GET request this route fetches the KPIs assigned to the
    employee's position via the `puesto_kpis` table and displays a form
    with current values (if any).  It also lists the KPIs for all
    subordinate employees so that a supervisor can fill them in.  On a
    POST request it processes the submitted KPI results for the target
    employee.
    """
    empleado_id = session.get("empleado_id")
    if empleado_id is None:
        flash("Tu usuario no tiene un empleado asociado", "warning")
        return redirect(url_for("logout"))
    conn = get_db_connection()
    period = current_period()
    if request.method == "POST":
        # Determine for which employee the KPI results are being submitted.
        target_empleado_id = request.form.get("target_empleado_id")
        if not target_empleado_id:
            target_empleado_id = str(empleado_id)
        # For each KPI id sent in the form, update or insert the result
        kpi_ids = request.form.getlist("kpi_id")
        values = request.form.getlist("valor")
        textos = request.form.getlist("texto_resultado")
        # We will use transaction to update results
        try:
            with conn.cursor() as cur:
                for kpi_id, valor, texto in zip(kpi_ids, values, textos):
                    # Determine if the KPI is a criterio (text-only)
                    cur.execute("SELECT es_criterio FROM kpis WHERE id=%s", (kpi_id,))
                    row = cur.fetchone()
                    es_criterio = row["es_criterio"] if row else False
                    if es_criterio:
                        valor_db = None
                        texto_db = texto
                    else:
                        try:
                            valor_db = float(valor) if valor else None
                        except ValueError:
                            valor_db = None
                        texto_db = None
                    # Check if result exists
                    cur.execute(
                        "SELECT id FROM kpi_resultados WHERE empleado_id=%s AND kpi_id=%s AND periodo=%s",
                        (target_empleado_id, kpi_id, period),
                    )
                    existing = cur.fetchone()
                    if existing:
                        # Update
                        cur.execute(
                            "UPDATE kpi_resultados SET valor=%s, texto_resultado=%s WHERE id=%s",
                            (valor_db, texto_db, existing["id"]),
                        )
                    else:
                        # Insert
                        cur.execute(
                            "INSERT INTO kpi_resultados (empleado_id, kpi_id, periodo, valor, texto_resultado) VALUES (%s, %s, %s, %s, %s)",
                            (target_empleado_id, kpi_id, period, valor_db, texto_db),
                        )
            flash("KPIs guardados correctamente", "success")
        finally:
            conn.close()
        # redirect to avoid resubmission
        return redirect(url_for("mis_kpis"))
    else:
        # GET request: show the form
        with conn.cursor() as cur:
            # Fetch current employee and position
            cur.execute(
                "SELECT e.id, e.nombre, p.id AS puesto_id, p.nombre AS puesto_nombre "
                "FROM empleados e LEFT JOIN puestos p ON e.puesto_id=p.id WHERE e.id=%s",
                (empleado_id,),
            )
            emp = cur.fetchone()
            if not emp or not emp["puesto_id"]:
                conn.close()
                return render_template("mis_kpis_no_puesto.html")
            puesto_id = emp["puesto_id"]
            # Fetch KPIs assigned to this position
            cur.execute(
                "SELECT k.id, k.descripcion, k.unidad_medida, k.valor_objetivo, k.rango_rojo_min, "
                "k.rango_rojo_max, k.rango_amarillo_min, k.rango_amarillo_max, "
                "k.rango_verde_min, k.rango_verde_max, k.es_criterio, kr.valor, kr.texto_resultado "
                "FROM puesto_kpis pk "
                "JOIN kpis k ON pk.kpi_id = k.id "
                "LEFT JOIN kpi_resultados kr ON kr.kpi_id = k.id AND kr.empleado_id = %s AND kr.periodo = %s "
                "WHERE pk.puesto_id = %s "
                "ORDER BY k.descripcion",
                (empleado_id, period, puesto_id),
            )
            raw_kpis = cur.fetchall()
            my_kpis = []
            # compute color for each KPI
            for row in raw_kpis:
                color = None
                if not row["es_criterio"] and row["valor"] is not None:
                    val = row["valor"]
                    # Determine color based on ranges; assume that a value within verde range is best
                    # and amarillo is intermediate.  If ranges are null, no colour is applied.
                    # Note: ranges may be stored as None if not provided.
                    if (
                        row["rango_verde_min"] is not None
                        and row["rango_verde_max"] is not None
                        and row["rango_verde_min"] <= val <= row["rango_verde_max"]
                    ):
                        color = "success"
                    elif (
                        row["rango_amarillo_min"] is not None
                        and row["rango_amarillo_max"] is not None
                        and row["rango_amarillo_min"] <= val <= row["rango_amarillo_max"]
                    ):
                        color = "warning"
                    elif (
                        row["rango_rojo_min"] is not None
                        and row["rango_rojo_max"] is not None
                        and row["rango_rojo_min"] <= val <= row["rango_rojo_max"]
                    ):
                        color = "danger"
                row["color"] = color
                my_kpis.append(row)
            # Determine subordinates: employees whose position reports to this position
            cur.execute(
                "SELECT id FROM puestos WHERE jefe_puesto_id = %s",
                (puesto_id,),
            )
            subordinate_puestos = [row["id"] for row in cur.fetchall()]
            subordinate_data = []
            if subordinate_puestos:
                # Fetch employees whose positions are in the subordinate list
                format_strings = ",".join(["%s"] * len(subordinate_puestos))
                cur.execute(
                    f"SELECT e.id, e.nombre, p.id AS puesto_id, p.nombre AS puesto_nombre FROM empleados e "
                    f"JOIN puestos p ON e.puesto_id=p.id WHERE e.puesto_id IN ({format_strings})",
                    subordinate_puestos,
                )
                subordinate_emps = cur.fetchall()
                # For each subordinate employee, fetch their KPIs and results
                for sub in subordinate_emps:
                    # fetch kpis for subordinate's position
                    cur.execute(
                        "SELECT k.id, k.descripcion, k.unidad_medida, k.valor_objetivo, k.rango_rojo_min, "
                        "k.rango_rojo_max, k.rango_amarillo_min, k.rango_amarillo_max, "
                        "k.rango_verde_min, k.rango_verde_max, k.es_criterio, kr.valor, kr.texto_resultado "
                        "FROM puesto_kpis pk "
                        "JOIN kpis k ON pk.kpi_id=k.id "
                        "LEFT JOIN kpi_resultados kr ON kr.kpi_id=k.id AND kr.empleado_id=%s AND kr.periodo=%s "
                        "WHERE pk.puesto_id=%s ORDER BY k.descripcion",
                        (sub["id"], period, sub["puesto_id"]),
                    )
                    raw_sub_kpis = cur.fetchall()
                    kpi_list_sub = []
                    for r in raw_sub_kpis:
                        color = None
                        if not r["es_criterio"] and r["valor"] is not None:
                            val = r["valor"]
                            if (
                                r["rango_verde_min"] is not None
                                and r["rango_verde_max"] is not None
                                and r["rango_verde_min"] <= val <= r["rango_verde_max"]
                            ):
                                color = "success"
                            elif (
                                r["rango_amarillo_min"] is not None
                                and r["rango_amarillo_max"] is not None
                                and r["rango_amarillo_min"] <= val <= r["rango_amarillo_max"]
                            ):
                                color = "warning"
                            elif (
                                r["rango_rojo_min"] is not None
                                and r["rango_rojo_max"] is not None
                                and r["rango_rojo_min"] <= val <= r["rango_rojo_max"]
                            ):
                                color = "danger"
                        r["color"] = color
                        kpi_list_sub.append(r)
                    subordinate_data.append({"empleado": sub, "kpis": kpi_list_sub})
        conn.close()
        return render_template(
            "mis_kpis.html",
            my_kpis=my_kpis,
            empleado=emp,
            subordinates=subordinate_data,
            period=period,
        )


@app.route("/cerrar_periodo", methods=["POST"])
@require_login
def cerrar_periodo():
    """Mark the KPI results for a given employee and month as closed.

    The direct supervisor of an employee (or the employee themselves if
    they have no supervisor) can close the KPI period.  Closing is
    implemented by setting the `cerrado` flag to 1 for all results of
    that employee and period.
    """
    empleado_id = session.get("empleado_id")
    target_empleado_id = request.form.get("empleado_id") or empleado_id
    period = current_period()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE kpi_resultados SET cerrado=1, cerrado_por=%s WHERE empleado_id=%s AND periodo=%s",
                (empleado_id, target_empleado_id, period),
            )
        flash("Periodo cerrado correctamente", "success")
    finally:
        conn.close()
    return redirect(url_for("mis_kpis"))


# ----------------------------------------------------------------------------
# KPI catalog management
# ----------------------------------------------------------------------------

@app.route("/kpis", methods=["GET", "POST"])
@require_login
def kpis():
    """View and manage KPI definitions.

    Supports searching by id, description or department.  Allows
    creation of new KPIs via a collapsible generator section.  KPIs can
    be edited in-place using a modal dialog.  When creating or editing
    KPIs you must provide at least a description; for metric KPIs you
    also provide units, objective values and threshold ranges; for
    criterio KPIs leave these numeric fields blank.
    """
    conn = get_db_connection()
    # Handle creation of new KPI
    if request.method == "POST" and request.form.get("action") == "create_kpi":
        descripcion = request.form.get("descripcion")
        unidad = request.form.get("unidad_medida") or None
        objetivo = request.form.get("valor_objetivo") or None
        try:
            objetivo_val = float(objetivo) if objetivo else None
        except ValueError:
            objetivo_val = None
        # Ranges for rojo, amarillo, verde (min and max).  Input names use suffixes.
        def parse_range(prefix: str):
            min_val = request.form.get(f"{prefix}_min") or None
            max_val = request.form.get(f"{prefix}_max") or None
            try:
                min_val = float(min_val) if min_val else None
            except ValueError:
                min_val = None
            try:
                max_val = float(max_val) if max_val else None
            except ValueError:
                max_val = None
            return (min_val, max_val)

        rojo_min, rojo_max = parse_range("rojo")
        amarillo_min, amarillo_max = parse_range("amarillo")
        verde_min, verde_max = parse_range("verde")
        es_criterio = request.form.get("es_criterio") == "on"
        departamento_id = request.form.get("departamento_id") or None
        if not descripcion:
            flash("Debes ingresar una descripción para el KPI", "danger")
        else:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO kpis (descripcion, unidad_medida, valor_objetivo, rango_rojo_min, rango_rojo_max, "
                    "rango_amarillo_min, rango_amarillo_max, rango_verde_min, rango_verde_max, es_criterio, departamento_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        descripcion,
                        unidad,
                        objetivo_val,
                        rojo_min,
                        rojo_max,
                        amarillo_min,
                        amarillo_max,
                        verde_min,
                        verde_max,
                        es_criterio,
                        departamento_id if departamento_id else None,
                    ),
                )
            flash("KPI creado correctamente", "success")
        return redirect(url_for("kpis"))
    # Searching
    query = request.args.get("q", "").strip()
    kpi_list = []
    departamentos = []
    with conn.cursor() as cur:
        cur.execute("SELECT id, nombre FROM departamentos ORDER BY nombre")
        departamentos = cur.fetchall()
        if query:
            cur.execute(
                "SELECT k.*, d.nombre AS depto FROM kpis k "
                "LEFT JOIN departamentos d ON k.departamento_id=d.id "
                "WHERE k.id LIKE %s OR k.descripcion LIKE %s OR d.nombre LIKE %s "
                "ORDER BY k.descripcion", (
                    f"%{query}%",
                    f"%{query}%",
                    f"%{query}%",
                ),
            )
        else:
            cur.execute(
                "SELECT k.*, d.nombre AS depto FROM kpis k "
                "LEFT JOIN departamentos d ON k.departamento_id=d.id ORDER BY k.descripcion"
            )
        kpi_list = cur.fetchall()
    conn.close()
    return render_template(
        "kpis.html",
        kpis=kpi_list,
        departamentos=departamentos,
        query=query,
    )


@app.route("/kpis/<int:kpi_id>", methods=["POST"])
@require_login
def edit_kpi(kpi_id):
    """Update an existing KPI.  The data is submitted via a modal form.

    All fields have the same semantics as the create route.  If a field
    is left blank the corresponding column will be set to NULL.  Once
    updated the user is redirected back to the KPI list with a flash
    message.
    """
    conn = get_db_connection()
    descripcion = request.form.get("descripcion")
    unidad = request.form.get("unidad_medida") or None
    objetivo = request.form.get("valor_objetivo") or None
    try:
        objetivo_val = float(objetivo) if objetivo else None
    except ValueError:
        objetivo_val = None
    def parse_range(prefix: str):
        min_val = request.form.get(f"{prefix}_min") or None
        max_val = request.form.get(f"{prefix}_max") or None
        try:
            min_val = float(min_val) if min_val else None
        except ValueError:
            min_val = None
        try:
            max_val = float(max_val) if max_val else None
        except ValueError:
            max_val = None
        return (min_val, max_val)
    rojo_min, rojo_max = parse_range("rojo")
    amarillo_min, amarillo_max = parse_range("amarillo")
    verde_min, verde_max = parse_range("verde")
    es_criterio = request.form.get("es_criterio") == "on"
    departamento_id = request.form.get("departamento_id") or None
    if not descripcion:
        flash("La descripción del KPI no puede estar vacía", "danger")
        return redirect(url_for("kpis"))
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE kpis SET descripcion=%s, unidad_medida=%s, valor_objetivo=%s, "
            "rango_rojo_min=%s, rango_rojo_max=%s, rango_amarillo_min=%s, rango_amarillo_max=%s, "
            "rango_verde_min=%s, rango_verde_max=%s, es_criterio=%s, departamento_id=%s WHERE id=%s",
            (
                descripcion,
                unidad,
                objetivo_val,
                rojo_min,
                rojo_max,
                amarillo_min,
                amarillo_max,
                verde_min,
                verde_max,
                es_criterio,
                departamento_id if departamento_id else None,
                kpi_id,
            ),
        )
    conn.close()
    flash("KPI actualizado correctamente", "success")
    return redirect(url_for("kpis"))


# ----------------------------------------------------------------------------
# Positions management
# ----------------------------------------------------------------------------

@app.route("/puestos", methods=["GET", "POST"])
@require_login
def puestos():
    """Manage positions (puestos).

    This view lists existing positions with their department and allows
    editing of the name, department and hierarchical relationships.  It
    also provides a modal to assign KPIs to a position.  New positions
    can be created from this page.
    """
    conn = get_db_connection()
    # Handle creation of a new position
    if request.method == "POST" and request.form.get("action") == "create_puesto":
        nombre = request.form.get("nombre")
        departamento_id = request.form.get("departamento_id") or None
        jefe_puesto_id = request.form.get("jefe_puesto_id") or None
        if not nombre:
            flash("El nombre del puesto no puede estar vacío", "danger")
        else:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO puestos (nombre, departamento_id, jefe_puesto_id) VALUES (%s, %s, %s)",
                    (nombre, departamento_id if departamento_id else None, jefe_puesto_id if jefe_puesto_id else None),
                )
            flash("Puesto creado correctamente", "success")
        return redirect(url_for("puestos"))
    # Handle assignment of KPIs to a position
    if request.method == "POST" and request.form.get("action") == "asignar_kpis":
        puesto_id = request.form.get("puesto_id")
        kpi_ids = request.form.getlist("kpis")
        with conn.cursor() as cur:
            # remove old assignments
            cur.execute("DELETE FROM puesto_kpis WHERE puesto_id=%s", (puesto_id,))
            # insert new assignments
            for kpi_id in kpi_ids:
                cur.execute("INSERT INTO puesto_kpis (puesto_id, kpi_id) VALUES (%s, %s)", (puesto_id, kpi_id))
        flash("KPIs asignados correctamente", "success")
        return redirect(url_for("puestos"))
    # Handle editing of a position
    if request.method == "POST" and request.form.get("action") == "edit_puesto":
        puesto_id = request.form.get("puesto_id")
        nombre = request.form.get("nombre")
        departamento_id = request.form.get("departamento_id") or None
        jefe_puesto_id = request.form.get("jefe_puesto_id") or None
        if not nombre:
            flash("El nombre del puesto no puede estar vacío", "danger")
        else:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE puestos SET nombre=%s, departamento_id=%s, jefe_puesto_id=%s WHERE id=%s",
                    (
                        nombre,
                        departamento_id if departamento_id else None,
                        jefe_puesto_id if jefe_puesto_id else None,
                        puesto_id,
                    ),
                )
            flash("Puesto actualizado correctamente", "success")
        return redirect(url_for("puestos"))
    # Otherwise, display the list
    with conn.cursor() as cur:
        # fetch positions
        cur.execute(
            "SELECT p.id, p.nombre, d.nombre AS departamento, p.jefe_puesto_id, pj.nombre AS jefe_nombre "
            "FROM puestos p "
            "LEFT JOIN departamentos d ON p.departamento_id=d.id "
            "LEFT JOIN puestos pj ON p.jefe_puesto_id=pj.id "
            "ORDER BY p.nombre"
        )
        puestos_list = cur.fetchall()
        # fetch departments for selects
        cur.execute("SELECT id, nombre FROM departamentos ORDER BY nombre")
        departamentos = cur.fetchall()
        # fetch all positions for boss selection
        cur.execute("SELECT id, nombre FROM puestos ORDER BY nombre")
        puestos_simple = cur.fetchall()
        # fetch KPIs for assignment modal
        cur.execute("SELECT id, descripcion FROM kpis ORDER BY descripcion")
        kpis = cur.fetchall()
        # fetch assigned KPIs for each position to pre-check boxes
        cur.execute("SELECT puesto_id, kpi_id FROM puesto_kpis")
        assignments = cur.fetchall()
    conn.close()
    # build map of assigned kpi ids per puesto
    assigned_map: dict[int, list[int]] = {}
    for row in assignments:
        assigned_map.setdefault(row["puesto_id"], []).append(row["kpi_id"])
    return render_template(
        "puestos.html",
        puestos=puestos_list,
        departamentos=departamentos,
        puestos_simple=puestos_simple,
        kpis=kpis,
        assigned_map=assigned_map,
    )


# ----------------------------------------------------------------------------
# Personal management
# ----------------------------------------------------------------------------

@app.route("/personal", methods=["GET", "POST"])
@require_login
def personal():
    """Display, import and edit employee records (with pagination).

    - List is paginated (100 per page) to keep the UI fast with large datasets.
    - Search (q) is applied to the full table and results are paginated.
    - Default ordering is alphabetical by employee name.
    - Select lists (puestos, jefes) are ordered alphabetically by name.
    - Import from incidencias normalizes employee_number to 5 digits (zfill(5))
      to avoid duplicates (e.g. 123 -> 00123).
    """

    def normalize_emp_id(value) -> str:
        if value is None:
            return ""
        s = str(value).strip()
        # Some sources may provide numeric ids; keep only digits if possible,
        # then left-pad to 5. If it isn't purely digits, still pad the raw string.
        digits = "".join(ch for ch in s if ch.isdigit())
        base = digits if digits else s
        return base.zfill(5)

    conn = get_db_connection()

    # -----------------------------
    # Edit employee
    # -----------------------------
    if request.method == "POST" and request.form.get("action") == "edit_empleado":
        empleado_id = request.form.get("empleado_id")
        nombre = (request.form.get("nombre") or "").strip()
        puesto_id = request.form.get("puesto_id") or None
        jefe_directo_id = request.form.get("jefe_directo_id") or None
        email = (request.form.get("email") or "").strip() or None

        if not nombre:
            flash("El nombre del empleado no puede estar vacío", "danger")
        else:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE empleados SET nombre=%s, puesto_id=%s, jefe_directo_id=%s, email=%s WHERE id=%s",
                    (
                        nombre,
                        puesto_id if puesto_id else None,
                        jefe_directo_id if jefe_directo_id else None,
                        email,
                        empleado_id,
                    ),
                )
            flash("Empleado actualizado correctamente", "success")
        conn.close()
        return redirect(url_for("personal"))

    # -----------------------------
    # Import from incidencias
    # -----------------------------
    if request.method == "POST" and request.form.get("action") == "importar":
        imported = 0
        inc_conn = get_incidencias_connection()
        if not inc_conn:
            flash("La base de datos de incidencias no está configurada", "danger")
            conn.close()
            return redirect(url_for("personal"))

        with inc_conn.cursor() as inc_cur:
            inc_cur.execute("SELECT employee_number, full_name, puesto, department_name FROM personal")
            remote_rows = inc_cur.fetchall()
        inc_conn.close()

        if not remote_rows:
            flash("No se encontraron registros en la base de incidencias", "warning")
            conn.close()
            return redirect(url_for("personal"))

        with conn.cursor() as cur:
            # Existing ids normalized to 5 digits to avoid duplicates
            cur.execute("SELECT id_empleado FROM empleados")
            existing_ids = {normalize_emp_id(row["id_empleado"]) for row in cur.fetchall() if row.get("id_empleado")}

            for row in remote_rows:
                emp_id = normalize_emp_id(row.get("employee_number"))
                if not emp_id or emp_id in existing_ids:
                    continue

                nombre = (row.get("full_name") or "").strip()
                puesto_nombre = (row.get("puesto") or "").strip() or None
                dept_nombre = (row.get("department_name") or "").strip() or None

                # Find or create department
                departamento_id = None
                if dept_nombre:
                    cur.execute("SELECT id FROM departamentos WHERE nombre=%s", (dept_nombre,))
                    drow = cur.fetchone()
                    if drow:
                        departamento_id = drow["id"]
                    else:
                        cur.execute("INSERT INTO departamentos (nombre) VALUES (%s)", (dept_nombre,))
                        departamento_id = cur.lastrowid

                # Find or create position
                puesto_id = None
                if puesto_nombre:
                    cur.execute("SELECT id FROM puestos WHERE nombre=%s", (puesto_nombre,))
                    prow = cur.fetchone()
                    if prow:
                        puesto_id = prow["id"]
                    else:
                        cur.execute(
                            "INSERT INTO puestos (nombre, departamento_id) VALUES (%s, %s)",
                            (puesto_nombre, departamento_id),
                        )
                        puesto_id = cur.lastrowid

                cur.execute(
                    "INSERT INTO empleados (id_empleado, nombre, puesto_id) VALUES (%s, %s, %s)",
                    (emp_id, nombre, puesto_id),
                )
                imported += 1
                existing_ids.add(emp_id)

        flash(f"Se importaron {imported} empleados nuevos desde incidencias", "success")
        conn.close()
        return redirect(url_for("personal"))

    # -----------------------------
    # GET: list employees (paged)
    # -----------------------------
    query = (request.args.get("q") or "").strip()
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    page = max(1, page)
    page_size = 100
    offset = (page - 1) * page_size

    where_sql = ""
    params = []
    if query:
        where_sql = "WHERE e.id_empleado LIKE %s OR e.nombre LIKE %s"
        params.extend([f"%{query}%", f"%{query}%"])

    with conn.cursor() as cur:
        # Count total for pagination (search applies to full table)
        cur.execute(f"SELECT COUNT(*) AS total FROM empleados e {where_sql}", params)
        total_count = (cur.fetchone() or {}).get("total", 0) or 0
        total_pages = max(1, math.ceil(total_count / page_size)) if total_count else 1
        if page > total_pages:
            page = total_pages
            offset = (page - 1) * page_size

        # Page query
        cur.execute(
            "SELECT e.id, e.id_empleado, e.nombre, p.id AS puesto_id, p.nombre AS puesto_nombre, "
            "j.id AS jefe_id, j.nombre AS jefe_nombre, e.email "
            "FROM empleados e "
            "LEFT JOIN puestos p ON e.puesto_id=p.id "
            "LEFT JOIN empleados j ON e.jefe_directo_id=j.id "
            f"{where_sql} "
            "ORDER BY e.nombre ASC "
            "LIMIT %s OFFSET %s",
            params + [page_size, offset],
        )
        empleados_list = cur.fetchall()

        # Select lists ordered alphabetically
        cur.execute("SELECT id, nombre FROM puestos ORDER BY nombre ASC")
        puestos_simple = cur.fetchall()
        cur.execute("SELECT id, nombre FROM empleados ORDER BY nombre ASC")
        jefes_simple = cur.fetchall()

    conn.close()
    return render_template(
        "personal.html",
        empleados=empleados_list,
        puestos=puestos_simple,
        jefes=jefes_simple,
        query=query,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        page_size=page_size,
    )


# ----------------------------------------------------------------------------
# Organigram
# ----------------------------------------------------------------------------

@app.route("/organigrama")
@require_login
def organigrama():
    """Render the organisational chart page.

    The organigram is generated on the client side using jsTree.  The
    server provides a JSON endpoint (/organigrama/data) that returns
    hierarchical data representing the positions and their employees.
    Drag-and-drop events are captured client side and posted to the
    /organigrama/move endpoint.
    """
    return render_template("organigrama.html")


@app.route("/organigrama/data")
@require_login
def organigrama_data():
    """Return hierarchical data of the organisation in JSON format.

    Each position is represented as a node, with its employees as
    children.  Positions that report to another position are nested
    accordingly.  The top-level nodes are positions without a boss.
    """
    conn = get_db_connection()
    with conn.cursor() as cur:
        # fetch all positions
        cur.execute("SELECT id, nombre, jefe_puesto_id FROM puestos")
        puestos = cur.fetchall()
        # fetch all employees
        cur.execute("SELECT id, nombre, puesto_id FROM empleados")
        empleados = cur.fetchall()
    conn.close()
    # Build a tree structure: for each puesto create node
    nodes = {p["id"]: {"id": f"puesto_{p['id']}", "text": p["nombre"], "children": []} for p in puestos}
    # attach employees to their position
    for emp in empleados:
        puesto_id = emp["puesto_id"]
        if puesto_id and puesto_id in nodes:
            nodes[puesto_id]["children"].append({
                "id": f"empleado_{emp['id']}",
                "text": emp["nombre"],
                "icon": "fas fa-user text-secondary",
                "li_attr": {"data-employee-id": emp["id"]},
            })
    # attach child positions to their parent position
    forest = []
    for p in puestos:
        node = nodes[p["id"]]
        jefe = p["jefe_puesto_id"]
        if jefe and jefe in nodes:
            nodes[jefe]["children"].append(node)
        else:
            forest.append(node)
    return jsonify(forest)


@app.route("/organigrama/move", methods=["POST"])
@require_login
def organigrama_move():
    """Handle moving an employee to another position.

    The client sends the employee id and the new position id.  We
    update the employee's puesto_id and jefe_directo_id accordingly.
    """
    emp_id = request.json.get("employee_id")
    new_puesto_id = request.json.get("puesto_id")
    if not emp_id or not new_puesto_id:
        return jsonify({"error": "Datos incompletos"}), 400
    conn = get_db_connection()
    with conn.cursor() as cur:
        # update puesto
        cur.execute(
            "UPDATE empleados SET puesto_id=%s WHERE id=%s",
            (new_puesto_id, emp_id),
        )
        # update jefe_directo_id based on puesto's boss
        cur.execute("SELECT jefe_puesto_id FROM puestos WHERE id=%s", (new_puesto_id,))
        row = cur.fetchone()
        jefe_puesto_id = row["jefe_puesto_id"] if row else None
        if jefe_puesto_id:
            # find an employee occupying the boss position to assign as jefe_directo
            cur.execute(
                "SELECT id FROM empleados WHERE puesto_id=%s LIMIT 1",
                (jefe_puesto_id,),
            )
            boss_emp = cur.fetchone()
            jefe_emp_id = boss_emp["id"] if boss_emp else None
        else:
            jefe_emp_id = None
        cur.execute(
            "UPDATE empleados SET jefe_directo_id=%s WHERE id=%s",
            (jefe_emp_id, emp_id),
        )
    conn.close()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True)