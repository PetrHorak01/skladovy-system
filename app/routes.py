from flask_wtf import FlaskForm
from wtforms import SelectField, IntegerField, SubmitField
from wtforms.validators import DataRequired, NumberRange
from flask import (
    render_template, redirect, url_for, flash,
    request, session, current_app, make_response, send_file
)
from flask_login import login_user, logout_user, current_user, login_required
from app import app, db
from app.models import (
    User, Product, Stock, History,
    Transfer, TransferItem, Sales, Overtime
)
from app.forms import (
    LoginForm, AddProductForm, StockForm,
    NaskladnitForm, VyskladnitForm, UserForm, InventuraForm
)
from datetime import datetime
from collections import defaultdict
from weasyprint import HTML
from io import BytesIO
from sqlalchemy import func

def _parse_qty_form(form):
    """
    Z request.form vezme všechny klíče začínající na 'qty_'
    a vrátí dict ve tvaru {pid_str: {size_str: qty_int}} pouze s vyplněnými poli.
    """
    inv = {}
    for key, val in form.items():
        if not key.startswith("qty_"):
            continue
        # klíč má formát 'qty_<pid>_<size>'
        _, pid, size = key.split("_", 2)
        if val.strip() == "":
            continue
        try:
            qty = int(val)
        except ValueError:
            continue
        inv.setdefault(pid, {})[size] = qty
    return inv

@app.route("/", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        flash("Neplatné přihlašovací údaje", "danger")
    return render_template("login.html", form=form)


@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    sklady = ["Praha", "Brno", "Pardubice", "Ostrava", "Celkem"]
    selected_sklad = request.args.get("sklad") or current_user.sklad or "Praha"
    hledat = request.args.get("hledat", "").strip().lower()
    active_tab = request.args.get("tab", "saty")

    produkty_q = Product.query
    if hledat:
        produkty_q = produkty_q.filter(Product.name.ilike(f"%{hledat}%"))
    produkty = produkty_q.order_by(Product.name).all()

    velikosti_saty = list(range(32, 56, 2))
    velikosti_boty = list(range(36, 43))

    # Na všechny kategorie doplňky a ostatní budeme považovat za velikost 0
    stock_rows = (
        db.session.query(
            Stock.product_id,
            Stock.size,
            func.sum(Stock.quantity).label("qty")
        )
        .filter(
            (Stock.sklad == selected_sklad)
            if selected_sklad != "Celkem"
            else True
        )
        .group_by(Stock.product_id, Stock.size)
        .having(func.sum(Stock.quantity) > 0)
        .all()
    )
    qty_map = defaultdict(dict)
    for pid, size, qty in stock_rows:
        qty_map[pid][size] = qty

    tabulka_saty = []
    tabulka_boty = []
    tabulka_doplnky = []
    tabulka_ostatni = []

    for p in produkty:
        base = {
            "id": p.id,
            "name": p.name,
            "color": p.color,
            "back_solution": p.back_solution,
            "sizes": qty_map.get(p.id, {})
        }
        if p.category == "saty":
            tabulka_saty.append(base)
        elif p.category == "boty":
            tabulka_boty.append(base)
        elif p.category == "doplnky":
            tabulka_doplnky.append(base)
        elif p.category == "ostatni":
            tabulka_ostatni.append(base)

    stocks = {}
    for p in produkty:
        # poznámka = velikost 0
        note = Stock.query.filter_by(
            product_id=p.id, size=0, sklad=selected_sklad
        ).first()
        if note:
            stocks[(p.id, 0, selected_sklad)] = note
        sizes = (
            velikosti_saty if p.category == "saty"
            else velikosti_boty if p.category == "boty"
            else [0]
        )
        for v in sizes:
            st = Stock.query.filter_by(
                product_id=p.id, size=v, sklad=selected_sklad
            ).first()
            if st:
                stocks[(p.id, v, selected_sklad)] = st

    return render_template(
        "dashboard.html",
        sklady=sklady,
        selected_sklad=selected_sklad,
        hledat=hledat,
        active_tab=active_tab,
        velikosti_saty=velikosti_saty,
        velikosti_boty=velikosti_boty,
        tabulka_saty=tabulka_saty,
        tabulka_boty=tabulka_boty,
        tabulka_doplnky=tabulka_doplnky,
        tabulka_ostatni=tabulka_ostatni,
        stocks=stocks
    )


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/produkty", methods=["GET", "POST"])
@login_required
def produkty():
    if current_user.role != "admin":
        flash("Přístup odepřen.")
        return redirect(url_for("dashboard"))

    kategorie = ["saty", "boty", "doplnky", "ostatni"]
    vybrana_kategorie = request.args.get("kategorie", "saty")
    if vybrana_kategorie not in kategorie:
        vybrana_kategorie = "saty"

    form = AddProductForm()
    if form.validate_on_submit():
        produkt = Product(
            name=form.name.data,
            category=vybrana_kategorie,
            color=form.color.data if vybrana_kategorie in ["saty", "doplnky"] else None,
            back_solution=form.back_solution.data if vybrana_kategorie == "saty" else None
        )
        db.session.add(produkt)
        db.session.flush()

        if vybrana_kategorie == "saty":
            velikosti = list(range(32, 56, 2))
        elif vybrana_kategorie == "boty":
            velikosti = list(range(36, 43))
        else:  # doplnky i ostatni
            velikosti = [0]

        for sklad in ["Praha", "Brno", "Pardubice", "Ostrava"]:
            for size in velikosti:
                db.session.add(Stock(
                    product_id=produkt.id,
                    sklad=sklad,
                    size=size,
                    quantity=0
                ))

        db.session.commit()
        flash("Produkt byl přidán.")
        return redirect(url_for("produkty", kategorie=vybrana_kategorie))

    produkty = Product.query.filter_by(category=vybrana_kategorie).order_by(Product.name).all()
    uprava = request.view_args.get("uprava", None)
    return render_template(
        "produkty.html",
        form=form,
        produkty=produkty,
        vybrana_kategorie=vybrana_kategorie,
        uprava=uprava
    )


@app.route("/produkty/edit/<int:product_id>", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    if current_user.role != "admin":
        flash("Přístup odepřen.")
        return redirect(url_for("dashboard"))

    produkt = Product.query.get_or_404(product_id)
    form = AddProductForm(obj=produkt)
    if form.validate_on_submit():
        produkt.name = form.name.data
        if produkt.category in ["saty", "doplnky"]:
            produkt.color = form.color.data
        if produkt.category == "saty":
            produkt.back_solution = form.back_solution.data
        db.session.commit()
        flash("Produkt upraven.")
        return redirect(url_for("produkty", kategorie=produkt.category))

    form.name.data = produkt.name
    form.color.data = produkt.color
    form.back_solution.data = produkt.back_solution
    produkty = Product.query.filter_by(category=produkt.category).order_by(Product.name).all()
    return render_template(
        "produkty.html",
        form=form,
        produkty=produkty,
        vybrana_kategorie=produkt.category,
        uprava=produkt.id
    )


@app.route("/produkty/delete/<int:product_id>", methods=["POST"])
@login_required
def delete_product(product_id):
    if current_user.role != "admin":
        flash("Přístup odepřen.")
        return redirect(url_for("dashboard"))

    produkt = Product.query.get_or_404(product_id)
    kategorie = produkt.category

    zasoby = Stock.query.filter_by(product_id=product_id).all()
    if any(z.quantity > 0 for z in zasoby):
        flash("Produkt nelze smazat – na skladech není nulové množství.")
        return redirect(url_for("produkty", kategorie=kategorie))

    for z in zasoby:
        db.session.delete(z)
    db.session.delete(produkt)
    db.session.commit()
    flash("Produkt byl smazán.")
    return redirect(url_for("produkty", kategorie=kategorie))


@app.route("/historie", methods=["GET", "POST"])
@login_required
def historie():
    query = History.query
    user_filter = request.args.get("user")
    sklad_filter = request.args.get("sklad")
    od_str = request.args.get("od")
    do_str = request.args.get("do")

    if user_filter and user_filter != "Všichni":
        query = query.filter_by(user=user_filter)
    if sklad_filter and sklad_filter != "Všechny":
        query = query.filter_by(sklad=sklad_filter)
    if od_str:
        od_date = datetime.strptime(od_str, "%d.%m.%Y")
        query = query.filter(History.timestamp >= od_date)
    if do_str:
        do_date = datetime.strptime(do_str, "%d.%m.%Y")
        query = query.filter(History.timestamp <= do_date)

    zaznamy_raw = query.order_by(History.timestamp.desc()).all()
    produkty_cache = {p.id: p for p in Product.query.all()}
    zaznamy = []
    for h in zaznamy_raw:
        prod = produkty_cache.get(h.product_id)
        label = prod.variant_label if prod else "-"
        zaznamy.append({
            "timestamp": h.timestamp.strftime("%d.%m.%Y %H:%M"),
            "user":      h.user,
            "sklad":     h.sklad,
            "produkt":   label,
            "size":      h.size or "-",
            "change":    h.change_type,
            "amount":    h.amount,
            "note":      h.note or "-"
        })

    users = ["Všichni"] + sorted({h.user for h in History.query.distinct(History.user)})
    sklady = ["Všechny"] + sorted({h.sklad for h in History.query.distinct(History.sklad)})

    return render_template(
        "historie.html",
        zaznamy=zaznamy,
        users=users,
        sklady=sklady,
        selected_user=user_filter or "Všichni",
        selected_sklad=sklad_filter or "Všechny",
        od=od_str or "",
        do=do_str or ""
    )


@app.route("/naskladnit", methods=["GET", "POST"])
@login_required
def naskladnit():
    sklady = ["Praha", "Pardubice", "Brno", "Ostrava"]
    allowed = ["saty", "doplnky", "boty", "ostatni"]
    vybrana_kategorie = request.values.get("kategorie", "saty")
    if vybrana_kategorie not in allowed:
        vybrana_kategorie = "saty"

    form = NaskladnitForm()
    if current_user.role == "admin":
        form.sklad.choices = [(s, s) for s in sklady]
    else:
        form.sklad.choices = [(current_user.sklad, current_user.sklad)]
        form.sklad.data = current_user.sklad

    produkty = (
        Product.query
               .filter_by(category=vybrana_kategorie)
               .order_by(Product.name)
               .all()
    )
    produkty_dict = {p.id: p for p in produkty}
    form.product_id.choices = [(p.id, p.variant_label) for p in produkty]

    form.size.coerce = str
    if vybrana_kategorie == "saty":
        form.size.choices = [(str(v), str(v)) for v in range(32, 56, 2)]
    elif vybrana_kategorie == "boty":
        form.size.choices = [(str(v), str(v)) for v in range(36, 43)]
    else:  # doplnky i ostatni
        form.size.choices = [("0", "0")]

    if request.method == "POST":
        selected_sklad = form.sklad.data
        if current_user.role != "admin" and selected_sklad != current_user.sklad:
            flash(f"Nemáte oprávnění pracovat se skladem {selected_sklad}.", "danger")
            return redirect(url_for("naskladnit", kategorie=vybrana_kategorie))

        try:
            pid = int(form.product_id.data)
            prod = produkty_dict[pid]
        except:
            flash("Neplatný produkt.", "danger")
            return redirect(url_for("naskladnit", kategorie=vybrana_kategorie))

        raw_sz = form.size.data
        size = int(raw_sz) if raw_sz != "" else None
        # pro doplnky a ostatni size bude 0
        if vybrana_kategorie in ["doplnky", "ostatni"]:
            size = 0

        try:
            qty = int(form.quantity.data)
            if qty < 0:
                raise ValueError
        except:
            flash("Zadejte platné nenegativní množství.", "danger")
            return redirect(url_for("naskladnit", kategorie=vybrana_kategorie))

        stock = Stock.query.filter_by(
            product_id=prod.id,
            sklad=selected_sklad,
            size=size
        ).first()

        if stock:
            stock.quantity += qty
        else:
            stock = Stock(
                product_id=prod.id,
                sklad=selected_sklad,
                size=size,
                quantity=qty
            )
            db.session.add(stock)

        db.session.add(History(
            user=current_user.username,
            sklad=selected_sklad,
            product_id=prod.id,
            size=size,
            change_type="naskladneni",
            amount=qty,
            timestamp=datetime.now()
        ))
        db.session.commit()

        flash(f"Naskladněno {qty} ks {prod.variant_label} do {selected_sklad}.", "success")
        return redirect(url_for("naskladnit", kategorie=vybrana_kategorie))

    return render_template(
        "naskladnit.html",
        form=form,
        vybrana_kategorie=vybrana_kategorie,
        produkty_dict=produkty_dict
    )


@app.route("/vyskladnit", methods=["GET", "POST"])
@login_required
def vyskladnit():
    sklady = ["Praha", "Pardubice", "Brno", "Ostrava"]
    allowed = ["saty", "doplnky", "boty", "ostatni"]
    vybrana_kategorie = request.values.get("kategorie", "saty")
    if vybrana_kategorie not in allowed:
        vybrana_kategorie = "saty"

    form = VyskladnitForm()
    if current_user.role == "admin":
        form.sklad.choices = [(s, s) for s in sklady]
    else:
        form.sklad.choices = [(current_user.sklad, current_user.sklad)]
        form.sklad.data = current_user.sklad

    produkty = (
        Product.query
               .filter_by(category=vybrana_kategorie)
               .order_by(Product.name)
               .all()
    )
    produkty_dict = {p.id: p for p in produkty}
    form.product_id.choices = [(p.id, p.variant_label) for p in produkty]

    form.size.coerce = str
    if vybrana_kategorie == "saty":
        form.size.choices = [(str(v), str(v)) for v in range(32, 56, 2)]
    elif vybrana_kategorie == "boty":
        form.size.choices = [(str(v), str(v)) for v in range(36, 43)]
    else:
        form.size.choices = [("0", "0")]

    if request.method == "POST":
        selected_sklad = form.sklad.data
        if current_user.role != "admin" and selected_sklad != current_user.sklad:
            flash(f"Nemáte oprávnění pracovat se skladem {selected_sklad}.", "danger")
            return redirect(url_for("vyskladnit", kategorie=vybrana_kategorie))

        try:
            pid = int(form.product_id.data)
            prod = produkty_dict[pid]
        except:
            flash("Neplatný produkt.", "danger")
            return redirect(url_for("vyskladnit", kategorie=vybrana_kategorie))

        raw_sz = form.size.data
        size = int(raw_sz) if raw_sz != "" else None
        if vybrana_kategorie in ["doplnky", "ostatni"]:
            size = 0

        try:
            qty = int(form.quantity.data)
            if qty < 0:
                raise ValueError
        except:
            flash("Zadejte platné nenegativní množství.", "danger")
            return redirect(url_for("vyskladnit", kategorie=vybrana_kategorie))

        stock = Stock.query.filter_by(
            product_id=prod.id,
            sklad=selected_sklad,
            size=size
        ).first()

        if not stock or stock.quantity < qty:
            flash(f"Nedostatek zásoby: {prod.variant_label}, vel. {size or '-'}", "danger")
            return redirect(url_for("vyskladnit", kategorie=vybrana_kategorie))

        stock.quantity -= qty
        db.session.add(History(
            user=current_user.username,
            sklad=selected_sklad,
            product_id=prod.id,
            size=size,
            change_type="vyskladneni",
            amount=-qty,
            timestamp=datetime.now()
        ))
        db.session.commit()

        flash(f"Vyskladněno {qty} ks {prod.variant_label} ze {selected_sklad}.", "success")
        return redirect(url_for("vyskladnit", kategorie=vybrana_kategorie))

    return render_template(
        "vyskladnit.html",
        form=form,
        vybrana_kategorie=vybrana_kategorie,
        produkty_dict=produkty_dict
    )


# ... ostatní trasy (přesuny, exporty, inventura) – u všech míst, kde byla None, se nyní používá 0 pro doplňky a ostatní

@app.route("/export/inventory", defaults={"sklad": None})
@app.route("/export/inventory/<sklad>")
@login_required
def export_inventory(sklad):
    sklady = ["Praha", "Brno", "Pardubice", "Ostrava"]

    if current_user.role == "admin" or current_user.sklad == "Pardubice":
        sklad = sklad or request.args.get("sklad", sklady[0])
        if sklad not in sklady:
            flash("Neplatný sklad.", "danger")
            return redirect(url_for("dashboard"))
    else:
        sklad = current_user.sklad
        if not sklad:
            flash("Nemáte přiřazen žádný sklad.", "danger")
            return redirect(url_for("dashboard"))

    velikosti = {
        "saty":    list(range(32, 56, 2)),
        "boty":    list(range(36, 43)),
        "doplnky": [0],
        "ostatni": [0],
    }

    produkty = Product.query.order_by(Product.name).all()
    products_by_category = {"saty": [], "boty": [], "doplnky": [], "ostatni": []}

    for p in produkty:
        if p.category in ["doplnky", "ostatni"]:
            st = Stock.query.filter_by(
                product_id=p.id,
                sklad=sklad,
                size=0
            ).first()
            qty = st.quantity if st else 0
            products_by_category[p.category].append({
                "name":     p.name,
                "color":    p.color,
                "quantity": qty
            })
        else:
            qtys = {}
            for v in velikosti[p.category]:
                st = Stock.query.filter_by(
                    product_id=p.id,
                    sklad=sklad,
                    size=v
                ).first()
                qtys[v] = st.quantity if st else 0
            products_by_category[p.category].append({
                "name":  p.name,
                "color": p.color,
                "sizes": qtys
            })

    html = render_template(
        "export_inventory.html",
        sklad=sklad,
        velikosti=velikosti,
        products_by_category=products_by_category
    )
    pdf_bytes = HTML(string=html, base_url=request.host_url).write_pdf()
    buf = BytesIO(pdf_bytes)
    filename = f"inventura_{sklad}.pdf"

    return send_file(
        buf,
        download_name=filename,
        mimetype="application/pdf",
        as_attachment=True
    )

@app.route("/inventura", methods=["GET", "POST"])
@login_required
def inventura():
    sklady = ["Praha", "Brno", "Pardubice", "Ostrava"]

    if current_user.role == "admin":
        sklad = request.values.get(
            "sklad",
            session.get("inventura_sklad", sklady[0])
        )
        session["inventura_sklad"] = sklad
    else:
        sklad = current_user.sklad
        if not sklad:
            flash("Nemáte přiřazen žádný sklad.", "danger")
            return redirect(url_for("dashboard"))

    velikosti = {
        "saty":    list(range(32, 56, 2)),
        "boty":    list(range(36, 43)),
        "doplnky": [0],
        "ostatni": [0],
    }

    if request.method == "POST":
        if "save_inventura" in request.form:
            session["inventura_data"] = _parse_qty_form(request.form)
            session.modified = True
            flash("Inventura dočasně uložena.", "success")
            return redirect(url_for("inventura", sklad=sklad))

        if "submit_inventura" in request.form:
            session["inventura_data"] = _parse_qty_form(request.form)
            session.modified = True

            inv = session["inventura_data"]
            diffs = []
            for pid_str, sizes in inv.items():
                pid = int(pid_str)
                for size_str, new_qty in sizes.items():
                    size = int(size_str) if size_str not in ("None", "") else 0
                    st = Stock.query.filter_by(
                        product_id=pid, sklad=sklad, size=size
                    ).first()
                    old_qty = st.quantity if st else 0
                    delta = new_qty - old_qty
                    if delta:
                        prod = Product.query.get(pid)
                        diffs.append({
                            "label": prod.variant_label,
                            "size": size,
                            "old": old_qty,
                            "new": new_qty,
                            "delta": delta
                        })

            return render_template(
                "inventura.html",
                mode="preview",
                sklad=sklad,
                sklady=sklady,
                diffs=diffs
            )

        if "confirm_inventura" in request.form:
            inv = session.pop("inventura_data", {})
            for pid_str, sizes in inv.items():
                pid = int(pid_str)
                for size_str, new_qty in sizes.items():
                    size = int(size_str) if size_str not in ("None", "") else 0
                    st = Stock.query.filter_by(product_id=pid, sklad=sklad, size=size).first()
                    old_qty = st.quantity if st else 0
                    delta = new_qty - old_qty

                    if st:
                        st.quantity = new_qty
                    else:
                        db.session.add(Stock(
                            product_id=pid,
                            sklad=sklad,
                            size=size,
                            quantity=new_qty
                        ))
                    if delta:
                        db.session.add(History(
                            user=current_user.username,
                            sklad=sklad,
                            product_id=pid,
                            size=size,
                            change_type="inventura",
                            amount=delta,
                            timestamp=datetime.now()
                        ))
            db.session.commit()
            flash("Inventura potvrzena a uložena.", "success")
            return redirect(url_for("inventura", sklad=sklad))

    inv = session.get("inventura_data", {})
    produkty = Product.query.order_by(Product.name).all()

    data_by_cat = {"saty": [], "boty": [], "doplnky": [], "ostatni": []}
    for p in produkty:
        kat = p.category
        row = {
            "product_id":    p.id,
            "name":          p.name,
            "color":         p.color,
            "back_solution": p.back_solution,
            "qtys":          {}
        }
        for v in velikosti[kat]:
            st = Stock.query.filter_by(
                product_id=p.id, sklad=sklad, size=v
            ).first()
            old_qty = st.quantity if st else 0
            new_qty = inv.get(str(p.id), {}).get(str(v), None)
            row["qtys"][v] = {"old": old_qty, "new": new_qty}
        data_by_cat[kat].append(row)

    return render_template(
        "inventura.html",
        mode="edit",
        sklad=sklad,
        sklady=sklady,
        velikosti=velikosti,
        data_by_cat=data_by_cat
    )
