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

# Konstanta pro "univerzální" velikost u produktů bez specifické velikosti
UNIVERSAL_SIZE = 0

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
            base["sizes"][UNIVERSAL_SIZE] = qty_map.get(p.id, {}).get(UNIVERSAL_SIZE, 0)
            tabulka_doplnky.append(base)
        elif p.category == "ostatni":
            base["sizes"][UNIVERSAL_SIZE] = qty_map.get(p.id, {}).get(UNIVERSAL_SIZE, 0)
            tabulka_ostatni.append(base)

    # --- OPTIMALIZACE ZAČÁTEK ---
    # Získání všech relevantních Stock objektů v jednom dotazu
    all_stock_records = Stock.query.filter(Stock.sklad == selected_sklad).all()

    # Zpracování do slovníku v paměti pro snadný přístup v šabloně
    stocks = {
        (stock.product_id, stock.size, stock.sklad): stock
        for stock in all_stock_records
    }
    # --- OPTIMALIZACE KONEC ---
    
    saty_grand_total = sum(sum(p['sizes'].values()) for p in tabulka_saty)
    boty_grand_total = sum(sum(p['sizes'].values()) for p in tabulka_boty)
    doplnky_grand_total = sum(p['sizes'].get(UNIVERSAL_SIZE, 0) for p in tabulka_doplnky)
    ostatni_grand_total = sum(p['sizes'].get(UNIVERSAL_SIZE, 0) for p in tabulka_ostatni)

  
    return render_template(
        "dashboard.html",
        sklady=sklady,
        selected_sklad=selected_sklad,
        hledat=hledat,
        active_tab=active_tab,
        velikosti_saty=velikosti_saty,
        velikosti_boty=velikosti_boty,
        universal_size=UNIVERSAL_SIZE,
        tabulka_saty=tabulka_saty,
        tabulka_boty=tabulka_boty,
        tabulka_doplnky=tabulka_doplnky,
        tabulka_ostatni=tabulka_ostatni,
        stocks=stocks,
        saty_grand_total=saty_grand_total,
        boty_grand_total=boty_grand_total,
        doplnky_grand_total=doplnky_grand_total,
        ostatni_grand_total=ostatni_grand_total
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
        else: # Pro doplnky a ostatni
            velikosti = [UNIVERSAL_SIZE]

        for sklad in ["Praha", "Brno", "Pardubice", "Ostrava"]:
            for size in velikosti:
                db.session.add(Stock(
                    product_id=produkt.id,
                    sklad=sklad,
                    size=size,
                    quantity=0
                ))
            # Záznam pro poznámku (= size=None, quantity=0) se vytváří pro všechny kategorie
            db.session.add(Stock(
                product_id=produkt.id,
                sklad=sklad,
                size=None,
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
    if any(z.quantity > 0 for z in zasoby if z.size is not None):
        flash("Produkt nelze smazat – na skladech není nulové množství.")
        return redirect(url_for("produkty", kategorie=kategorie))

    # Smazání všech záznamů ze Stock, včetně záznamu pro poznámku
    Stock.query.filter_by(product_id=product_id).delete()
    
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
        # Zobrazování velikosti
        size_display = "-"
        if h.size is not None:
            if prod and prod.category in ["doplnky", "ostatni"]:
                size_display = "-" # Pro doplňky/ostatní nezobrazujeme "velikost 0"
            else:
                size_display = str(h.size)

        zaznamy.append({
            "timestamp": h.timestamp.strftime("%d.%m.%Y %H:%M"),
            "user":      h.user,
            "sklad":     h.sklad,
            "produkt":   label,
            "size":      size_display,
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
    else:
        # Pro doplňky a ostatní je velikost pevně daná a nezobrazuje se jako volba
        form.size.choices = [(str(UNIVERSAL_SIZE), "-")]

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

        # Sjednocená logika pro získání velikosti
        raw_sz = form.size.data
        size = int(raw_sz) if raw_sz else None
        
        if vybrana_kategorie in ["doplnky", "ostatni"]:
            size = UNIVERSAL_SIZE

        try:
            qty = int(form.quantity.data)
            if qty < 0:
                raise ValueError
        except:
            flash("Zadejte platné nenegativní množství.", "danger")
            return redirect(url_for("naskladnit", kategorie=vybrana_kategorie))

        # Sjednocená logika pro vyhledání/vytvoření záznamu ve skladu
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
        # Pro doplňky a ostatní je velikost pevně daná a nezobrazuje se jako volba
        form.size.choices = [(str(UNIVERSAL_SIZE), "-")]

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

        # Sjednocená logika pro získání velikosti
        raw_sz = form.size.data
        size = int(raw_sz) if raw_sz else None

        if vybrana_kategorie in ["doplnky", "ostatni"]:
            size = UNIVERSAL_SIZE

        try:
            qty = int(form.quantity.data)
            if qty < 0:
                raise ValueError
        except:
            flash("Zadejte platné nenegativní množství.", "danger")
            return redirect(url_for("vyskladnit", kategorie=vybrana_kategorie))

        # Sjednocená logika pro vyhledání záznamu ve skladu
        stock = Stock.query.filter_by(
            product_id=prod.id,
            sklad=selected_sklad,
            size=size
        ).first()

        size_display = "-" if vybrana_kategorie in ["doplnky", "ostatni"] else size
        if not stock or stock.quantity < qty:
            flash(f"Nedostatek zásoby: {prod.variant_label}, vel. {size_display}", "danger")
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


@app.route("/uzivatele", methods=["GET", "POST"])
@login_required
def uzivatele():
    if current_user.role != "admin":
        flash("Přístup odepřen.", "danger")
        return redirect(url_for("dashboard"))

    form = UserForm()
    users = User.query.order_by(User.username).all()

    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("Uživatel s tímto jménem již existuje.", "warning")
            return redirect(url_for("uzivatele"))

        new_user = User(
            username=form.username.data,
            role=form.role.data,
            sklad=(form.sklad.data if form.role.data == "skladnik" else None)
        )
        new_user.set_password(form.password.data)

        db.session.add(new_user)
        db.session.commit()
        flash("Uživatel vytvořen.", "success")
        return redirect(url_for("uzivatele"))

    return render_template(
        "uzivatele.html",
        form=form,
        users=users,
        editing=None
    )


@app.route("/uzivatele/edit/<int:user_id>", methods=["GET", "POST"])
@login_required
def edit_user(user_id):
    if current_user.role != "admin":
        flash("Přístup odepřen.")
        return redirect(url_for("dashboard"))

    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user)

    if form.validate_on_submit():
        user.username = form.username.data
        user.set_password(form.password.data) # Heslo je třeba znovu zahashovat
        user.role = form.role.data
        user.sklad = form.sklad.data if user.role == "skladnik" else None
        db.session.commit()
        flash("Uživatel upraven.")
        return redirect(url_for("uzivatele"))

    return render_template(
        "uzivatele.html",
        form=form,
        users=User.query.order_by(User.username).all(),
        editing=user.id
    )


@app.route("/uzivatele/delete/<int:user_id>", methods=["POST"])
@login_required
def delete_user(user_id):
    if current_user.role != "admin":
        flash("Přístup odepřen.")
        return redirect(url_for("dashboard"))

    user = User.query.get_or_404(user_id)

    if user.username == current_user.username:
        flash("Nemůžete smazat sami sebe.")
        return redirect(url_for("uzivatele"))

    db.session.delete(user)
    db.session.commit()
    flash("Uživatel byl smazán.")
    return redirect(url_for("uzivatele"))


@app.route("/poznamka/<int:product_id>/<sklad>", methods=["POST"])
@login_required
def poznamka(product_id, sklad):
    note_text = request.form.get("note", "").strip()
    raw_sz = request.form.get("size", "")
    tab = request.form.get("tab", "saty")

    # --- ZAČÁTEK OPRAVY ---
    
    # Jasné a přímé určení velikosti.
    # Pokud je 'size' prázdný řetězec, jedná se o poznámku k celému produktu -> size = None.
    # Jinak se pokusíme hodnotu převést na číslo.
    size = None
    if raw_sz != "":
        try:
            size = int(raw_sz)
        except (ValueError, TypeError):
            # Pokud přijde nečíselná a neprázdná hodnota, je to chyba
            flash("Neplatná velikost v požadavku.", "danger")
            return redirect(url_for("dashboard", sklad=sklad, tab=tab) + f"#{tab}")
            
    # --- KONEC OPRAVY ---

    stock = Stock.query.filter_by(
        product_id=product_id,
        sklad=sklad,
        size=size
    ).first()

    if not stock:
        # Záznam v DB opravdu neexistuje. Zkusíme ho vytvořit.
        # To řeší problém s chybějícími záznamy pro starší produkty.
        stock = Stock(
            product_id=product_id,
            sklad=sklad,
            size=size,
            quantity=0  # Nově vytvořený záznam pro poznámku má 0 kusů
        )
        db.session.add(stock)
        # Není třeba db.session.commit() hned, provede se níže.

    stock.note = note_text

    # Záznam do historie provádíme vždy, když se změní poznámka
    history = History(
        user=current_user.username,
        sklad=sklad,
        product_id=product_id,
        size=size,
        change_type="poznamka",
        amount=0,
        timestamp=datetime.now(),
        note=note_text
    )
    db.session.add(history)
    db.session.commit()

    flash("Poznámka byla uložena.", "success")
    return redirect(
        url_for("dashboard", sklad=sklad, tab=tab) + f"#{tab}"
    )


@app.route("/prodeje")
@login_required
def prodeje():
    aktualni_datum = datetime.now()
    rok = aktualni_datum.year
    mesic = request.args.get("mesic")

    mesice = [
        (1, "Leden"), (2, "Únor"), (3, "Březen"), (4, "Duben"),
        (5, "Květen"), (6, "Červen"), (7, "Červenec"), (8, "Srpen"),
        (9, "Září"), (10, "Říjen"), (11, "Listopad"), (12, "Prosinec"),
        ("rocni_prehled", "Roční přehled")
    ]
    nazvy_mesicu = {str(m[0]): m[1] for m in mesice}
    vybrany_nazev = nazvy_mesicu.get(str(mesic), "")

    uzivatele = User.query.filter(User.role != "admin").order_by(User.username).all()
    jmena_uzivatelu = [u.username for u in uzivatele]

    data = defaultdict(lambda: {"zkousky": 0, "prodeje": 0})

    if mesic == "rocni_prehled":
        zaznamy = Sales.query.filter_by(year=rok).all()
        for z in zaznamy:
            data[z.user]["zkousky"] += z.tries
            data[z.user]["prodeje"] += z.sales
    else:
        mesic_int = int(mesic) if mesic else aktualni_datum.month
        zaznamy = Sales.query.filter_by(year=rok, month=mesic_int).all()
        for z in zaznamy:
            data[z.user]["zkousky"] = z.tries
            data[z.user]["prodeje"] = z.sales
        mesic = mesic_int

    for jmeno in jmena_uzivatelu:
        zk = data[jmeno]["zkousky"]
        pr = data[jmeno]["prodeje"]
        data[jmeno]["uspesnost"] = f"{(pr / zk * 100):.1f} %" if zk > 0 else "-"

    celkem_zkousky = sum(data[j]["zkousky"] for j in jmena_uzivatelu)
    celkem_prodeje = sum(data[j]["prodeje"] for j in jmena_uzivatelu)
    celkem_uspesnost = (
        f"{(celkem_prodeje / celkem_zkousky * 100):.1f} %"
        if celkem_zkousky > 0 else "-"
    )

    data["Celkem"] = {
        "zkousky":    celkem_zkousky,
        "prodeje":    celkem_prodeje,
        "uspesnost":  celkem_uspesnost
    }
    jmena_uzivatelu.append("Celkem")

    return render_template(
        "prodeje.html",
        mesice=mesice,
        vybrany_mesic=mesic,
        vybrany_nazev_mesice=nazvy_mesicu.get(str(mesic), "Roční přehled"),
        data=data,
        uzivatele=jmena_uzivatelu
    )


@app.route("/prodeje/zapsat", methods=["GET", "POST"])
@login_required
def zapsat_prodej():
    mesice = [
        (1, "Leden"), (2, "Únor"), (3, "Březen"), (4, "Duben"),
        (5, "Květen"), (6, "Červen"), (7, "Červenec"), (8, "Srpen"),
        (9, "Září"), (10, "Říjen"), (11, "Listopad"), (12, "Prosinec")
    ]
    nazvy_mesicu = {m[0]: m[1] for m in mesice}

    if request.method == "POST":
        try:
            zkusky = int(request.form.get("zkousky", 0))
            prodeje = int(request.form.get("prodeje", 0))
        except ValueError:
            flash("Zadejte platná čísla.")
            return redirect(url_for("prodeje"))

        username = current_user.username
        dnes = datetime.now()
        rok = dnes.year
        mesic = dnes.month

        if current_user.role == "admin":
            if "uzivatel" in request.form:
                username = request.form["uzivatel"]
            if "mesic" in request.form:
                try:
                    mesic = int(request.form["mesic"])
                except (ValueError, TypeError):
                    pass

        zaznam = Sales.query.filter_by(user=username, year=rok, month=mesic).first()
        if not zaznam:
            zaznam = Sales(user=username, year=rok, month=mesic, tries=0, sales=0)
            db.session.add(zaznam)

        zaznam.tries += zkusky
        zaznam.sales += prodeje

        timestamp = datetime.now()

        if zkusky != 0:
            db.session.add(History(
                user=current_user.username,
                sklad="Prodeje",
                product_id=None,
                size=None,
                change_type="zkoušky",
                amount=zkusky,
                timestamp=timestamp,
                note=f"{username} – {nazvy_mesicu[mesic]} {rok}"
            ))

        if prodeje != 0:
            db.session.add(History(
                user=current_user.username,
                sklad="Prodeje",
                product_id=None,
                size=None,
                change_type="prodej",
                amount=prodeje,
                timestamp=timestamp,
                note=f"{username} – {nazvy_mesicu[mesic]} {rok}"
            ))

        db.session.commit()
        flash("Prodej byl zapsán.")
        return redirect(url_for("prodeje", mesic=mesic))

    uzivatele = User.query.filter(User.role != "admin").order_by(User.username).all()
    return render_template(
        "zapsat_prodej.html",
        uzivatele=uzivatele,
        current_month=datetime.now().month,
        mesice=mesice
    )


@app.route("/prodeje/rocni")
@login_required
def prodeje_rocni():
    rok = datetime.now().year

    uzivatele = (
        User.query
            .filter(User.role != "admin")
            .order_by(User.username)
            .all()
    )
    jmena_uzivatelu = [u.username for u in uzivatele]

    data = defaultdict(lambda: {"zkousky": 0, "prodeje": 0})
    zaznamy = Sales.query.filter_by(year=rok).all()
    for z in zaznamy:
        data[z.user]["zkousky"] += z.tries
        data[z.user]["prodeje"] += z.sales

    for jmeno in jmena_uzivatelu:
        zk = data[jmeno]["zkousky"]
        pr = data[jmeno]["prodeje"]
        data[jmeno]["uspesnost"] = (
            f"{(pr / zk * 100):.1f} %" if zk > 0 else "-"
        )

    celkem_zkousky = sum(data[j]["zkousky"] for j in jmena_uzivatelu)
    celkem_prodeje = sum(data[j]["prodeje"] for j in jmena_uzivatelu)
    celkem_uspesnost = (
        f"{(celkem_prodeje / celkem_zkousky * 100):.1f} %"
        if celkem_zkousky > 0 else "-"
    )
    data["Celkem"] = {
        "zkousky":   celkem_zkousky,
        "prodeje":   celkem_prodeje,
        "uspesnost": celkem_uspesnost
    }
    jmena_uzivatelu.append("Celkem")

    return render_template(
        "prodeje_rocni.html",
        rok=rok,
        data=data,
        uzivatele=jmena_uzivatelu
    )


@app.route("/prescasy")
@login_required
def prescasy():
    aktualni_datum = datetime.now()
    rok = aktualni_datum.year
    mesic = request.args.get("mesic", aktualni_datum.month, type=int)

    mesice = [
        (1, "Leden"), (2, "Únor"), (3, "Březen"), (4, "Duben"),
        (5, "Květen"), (6, "Červen"), (7, "Červenec"), (8, "Srpen"),
        (9, "Září"), (10, "Říjen"), (11, "Listopad"), (12, "Prosinec")
    ]
    nazvy_mesicu = {m[0]: m[1] for m in mesice}
    vybrany_nazev_mesice = nazvy_mesicu.get(mesic, "")

    uzivatele = User.query.filter(User.role != "admin")\
                          .order_by(User.username).all()
    jmena_uzivatelu = [u.username for u in uzivatele]

    zaznamy = Overtime.query.filter_by(year=rok, month=mesic).all()
    data = defaultdict(lambda: {"classic": 0, "deluxe": 0})
    for z in zaznamy:
        data[z.user]["classic"] = z.classic
        data[z.user]["deluxe"] = z.deluxe

    celkem_classic = sum(data[j]["classic"] for j in jmena_uzivatelu)
    celkem_deluxe = sum(data[j]["deluxe"] for j in jmena_uzivatelu)
    data["Celkem"] = {
        "classic": celkem_classic,
        "deluxe":  celkem_deluxe
    }
    jmena_uzivatelu.append("Celkem")

    return render_template(
        "prescasy.html",
        mesice=mesice,
        vybrany_mesic=mesic,
        vybrany_nazev_mesice=vybrany_nazev_mesice,
        data=data,
        uzivatele=jmena_uzivatelu
    )


@app.route("/prescasy/zapsat", methods=["GET", "POST"])
@login_required
def zapsat_prescasy():
    mesice = [
        (1, "Leden"), (2, "Únor"), (3, "Březen"), (4, "Duben"),
        (5, "Květen"), (6, "Červen"), (7, "Červenec"), (8, "Srpen"),
        (9, "Září"), (10, "Říjen"), (11, "Listopad"), (12, "Prosinec")
    ]
    nazvy_mesicu = {m[0]: m[1] for m in mesice}

    if request.method == "POST":
        try:
            classic = int(request.form.get("classic", 0))
            deluxe = int(request.form.get("deluxe", 0))
        except ValueError:
            flash("Zadejte platná čísla.")
            return redirect(url_for("prescasy"))

        username = current_user.username
        if current_user.role == "admin" and "uzivatel" in request.form:
            username = request.form["uzivatel"]

        dnes = datetime.now()
        rok = dnes.year
        mesic = dnes.month

        if current_user.role == "admin" and "mesic" in request.form:
            try:
                mesic = int(request.form.get("mesic"))
            except (ValueError, TypeError):
                pass

        zaznam = Overtime.query.filter_by(user=username, year=rok, month=mesic).first()
        if not zaznam:
            zaznam = Overtime(user=username, year=rok, month=mesic, classic=0, deluxe=0)
            db.session.add(zaznam)

        zaznam.classic += classic
        zaznam.deluxe += deluxe

        now = datetime.now()

        if classic != 0:
            db.session.add(History(
                user=current_user.username,
                sklad="Přesčasy",
                product_id=None,
                size=None,
                change_type="classic přesčas",
                amount=classic,
                timestamp=now,
                note=f"{username} – {nazvy_mesicu[mesic]} {rok}"
            ))

        if deluxe != 0:
            db.session.add(History(
                user=current_user.username,
                sklad="Přesčasy",
                product_id=None,
                size=None,
                change_type="deluxe přesčas",
                amount=deluxe,
                timestamp=now,
                note=f"{username} – {nazvy_mesicu[mesic]} {rok}"
            ))

        db.session.commit()
        flash("Přesčasy byly zapsány.")
        return redirect(url_for("prescasy", mesic=mesic))

    uzivatele = User.query.filter(User.role != "admin").order_by(User.username).all()
    return render_template(
        "zapsat_prescasy.html",
        uzivatele=uzivatele,
        current_month=datetime.now().month,
        mesice=mesice
    )


@app.route("/prescasy/rocni")
@login_required
def prescasy_rocni():
    aktualni_rok = datetime.now().year

    uzivatele = (
        User.query
            .filter(User.role != "admin")
            .order_by(User.username)
            .all()
    )
    jmena_uzivatelu = [u.username for u in uzivatele]

    data = {}
    for jmeno in jmena_uzivatelu:
        zaznamy = Overtime.query.filter_by(user=jmeno, year=aktualni_rok).all()
        classic = sum(z.classic or 0 for z in zaznamy)
        deluxe = sum(z.deluxe or 0 for z in zaznamy)
        data[jmeno] = {"classic": classic, "deluxe": deluxe}

    celkem_classic = sum(data[j]["classic"] for j in jmena_uzivatelu)
    celkem_deluxe = sum(data[j]["deluxe"] for j in jmena_uzivatelu)
    data["Celkem"] = {"classic": celkem_classic, "deluxe": celkem_deluxe}
    jmena_uzivatelu.append("Celkem")

    return render_template(
        "prescasy_rocni.html",
        data=data,
        uzivatele=jmena_uzivatelu,
        rok=aktualni_rok
    )


@app.route("/preskladnit", methods=["GET", "POST"])
@login_required
def preskladnit():
    def ulozit_kosik_z_formulare():
        for it in session["kosik"]:
            pid = it["id"]
            prefix = f"velikost_{pid}_"
            for key, raw in request.form.items():
                if key.startswith(prefix):
                    suffix = key[len(prefix):]
                    try:
                        q = int(raw)
                    except (ValueError, TypeError):
                        continue
                    it["velikosti"][suffix] = max(0, q)
        session.modified = True

    sklady = ["Praha", "Brno", "Pardubice", "Ostrava"]
    default_source = (
        "Pardubice"
        if current_user.role == "admin" or current_user.sklad == "Pardubice"
        else current_user.sklad
    )
    source_sklad = request.values.get(
        "source_sklad",
        session.get("source_sklad", default_source)
    )
    session["source_sklad"] = source_sklad

    if not (current_user.role == "admin" or current_user.sklad == "Pardubice"):
        flash("Nemáte oprávnění zakládat přeskladnění.", "danger")
        return redirect(url_for("dashboard"))

    session.setdefault("kosik", [])
    session.setdefault("target_sklad", sklady[0])
    session.modified = True

    velikosti = {
        "saty":    list(range(32, 56, 2)),
        "boty":    list(range(36, 43)),
        "doplnky": [UNIVERSAL_SIZE],
        "ostatni": [UNIVERSAL_SIZE],
    }

    if request.method == "POST":
        ulozit_kosik_z_formulare()

        if "add_product" in request.form:
            pid = int(request.form["add_product"])
            if not any(it["id"] == pid for it in session["kosik"]):
                cat = Product.query.get(pid).category
                session["kosik"].append({
                    "id": pid,
                    "velikosti": {
                        str(v): 0 for v in velikosti[cat]
                    }
                })
            session.modified = True
            return redirect(url_for("preskladnit"))

        if "remove_product" in request.form:
            pid = int(request.form["remove_product"])
            session["kosik"] = [it for it in session["kosik"] if it["id"] != pid]
            session.modified = True
            return redirect(url_for("preskladnit"))

        if "preskladnit" in request.form:
            target = request.form.get("target_sklad", session["target_sklad"])
            session["target_sklad"] = target
            session.modified = True

            transfer = Transfer(
                source_sklad=source_sklad,
                target_sklad=target,
                created_by=current_user.username,
                created_at=datetime.now()
            )
            db.session.add(transfer)
            db.session.flush()

            try:
                for it in session["kosik"]:
                    prod = Product.query.get(it["id"])
                    for suffix, q in it["velikosti"].items():
                        try:
                            qty = int(q)
                            size = int(suffix)
                        except:
                            continue
                        if qty <= 0:
                            continue

                        sklad_z = Stock.query.filter_by(
                            product_id=prod.id,
                            sklad=source_sklad,
                            size=size
                        ).first()

                        size_display = "-" if prod.category in ["doplnky", "ostatni"] else size
                        if not sklad_z or sklad_z.quantity < qty:
                            raise ValueError(
                                f"Nedostatek zásoby: {prod.name}, vel. {size_display}"
                            )
                        sklad_z.quantity -= qty
                        db.session.add(History(
                            user=current_user.username,
                            sklad=source_sklad,
                            product_id=prod.id,
                            size=size,
                            change_type="preskladneni_vysklad",
                            amount=-qty,
                            timestamp=datetime.now()
                        ))
                        db.session.add(TransferItem(
                            transfer_id=transfer.id,
                            product_id=prod.id,
                            size=size,
                            quantity=qty
                        ))

                db.session.commit()
                session["kosik"] = []
                flash("Přeskladnění založeno – potvrďte v seznamu.", "success")
                return redirect(url_for("preskladneni_seznam"))
            except Exception as e:
                db.session.rollback()
                flash(str(e), "danger")
                return redirect(url_for("preskladnit"))

        if "tisk" in request.form:
            flash("Tisk zatím není implementován.", "info")
            return redirect(url_for("preskladnit"))

    produkty = Product.query.order_by(Product.name).all()
    produkty_podle_kategorii = {k: [] for k in velikosti.keys()}
    
    # --- OPTIMALIZACE ZDE ---
    # 1. Načteme všechny skladové zásoby pro zdrojový sklad najednou
    all_stock_for_sklad = Stock.query.filter_by(sklad=source_sklad).all()
    # 2. Vytvoříme slovník pro rychlé vyhledávání
    stock_map = {(s.product_id, s.size): s.quantity for s in all_stock_for_sklad}

    for p in produkty:
        qtys = {}
        for v in velikosti[p.category]:
            # 3. Místo dotazu do DB použijeme rychlé vyhledání
            qtys[v] = stock_map.get((p.id, v), 0)
            
        produkty_podle_kategorii[p.category].append({
            "id": p.id,
            "name": p.name,
            "color": p.color,
            "back_solution": p.back_solution,
            "velikosti": qtys
        })
    # --- KONEC OPTIMALIZACE ---

    normalized = []
    for it in session["kosik"]:
        sizes = {}
        for suffix, q in it["velikosti"].items():
            try:
                key = int(suffix)
                sizes[key] = int(q)
            except:
                continue
        normalized.append({"id": it["id"], "velikosti": sizes})

    produkty_dict = {p.id: p for p in produkty}
    kosik_saty = []
    kosik_boty = []
    kosik_doplnky = []
    kosik_ostatni = []
    for it in normalized:
        prod = produkty_dict[it["id"]]
        row = {
            "id": prod.id,
            "name": prod.name,
            "color": prod.color,
            "back_solution": prod.back_solution,
            "velikosti": it["velikosti"]
        }
        if prod.category == "saty":
            kosik_saty.append(row)
        elif prod.category == "boty":
            kosik_boty.append(row)
        elif prod.category == "doplnky":
            kosik_doplnky.append(row)
        else:
            kosik_ostatni.append(row)

    return render_template(
        "preskladnit.html",
        sklady=sklady,
        source_sklad=source_sklad,
        target_sklad=session["target_sklad"],
        produkty_podle_kategorii=produkty_podle_kategorii,
        kosik_saty=kosik_saty,
        kosik_boty=kosik_boty,
        kosik_doplnky=kosik_doplnky,
        kosik_ostatni=kosik_ostatni,
        velikosti=velikosti
    )

@app.route("/preskladneni/<int:transfer_id>", methods=["GET", "POST"])
@login_required
def preskladneni_detail(transfer_id):
    zpet = request.args.get("z", "seznam")
    transfer = Transfer.query.get_or_404(transfer_id)

    if not (
        current_user.role == "admin"
        or current_user.sklad == "Pardubice"
        or transfer.target_sklad == current_user.sklad
    ):
        flash("Nemáte oprávnění potvrdit toto přeskladnění.", "danger")
        return redirect(url_for("dashboard"))

    polozky = TransferItem.query.filter_by(transfer_id=transfer_id).all()

    if request.method == "POST" and transfer.status == "v_tranzitu":
        try:
            for pol in polozky:
                sklad_cil = Stock.query.filter_by(
                    product_id=pol.product_id,
                    sklad=transfer.target_sklad,
                    size=pol.size,
                ).first()
                if sklad_cil:
                    sklad_cil.quantity += pol.quantity
                else:
                    db.session.add(Stock(
                        product_id=pol.product_id,
                        sklad=transfer.target_sklad,
                        size=pol.size,
                        quantity=pol.quantity,
                    ))

                db.session.add(History(
                    user=current_user.username,
                    sklad=transfer.target_sklad,
                    product_id=pol.product_id,
                    size=pol.size,
                    change_type="preskladneni_nasklad",
                    amount=pol.quantity,
                    timestamp=datetime.now()
                ))

            transfer.status = "potvrzeno"
            transfer.confirmed_by = current_user.username
            transfer.confirmed_at = datetime.now()
            db.session.commit()
            flash("Přeskladnění potvrzeno a naskladněno.", "success")
            return redirect(url_for("preskladneni_seznam"))
        except Exception as e:
            db.session.rollback()
            flash(str(e), "danger")
            return redirect(url_for("preskladneni_detail", transfer_id=transfer_id, z=zpet))

    # příprava detailu (štítky apod.)
    produkty = {p.id: p for p in Product.query.all()}
    podrobnosti = []
    for pol in polozky:
        prod = produkty.get(pol.product_id)
        label = f"{prod.name}-{prod.color or '-'}-{prod.back_solution or '-'}" if prod else "-"
        size_display = "-" if prod and prod.category in ["doplnky", "ostatni"] else (pol.size or "-")
        podrobnosti.append({
            "label":    label,
            "size":     size_display,
            "quantity": pol.quantity,
        })

    return render_template(
        "preskladneni_detail.html",
        transfer=transfer,
        polozky=podrobnosti,
        zpet=zpet
    )

@app.route("/preskladneni_seznam")
@login_required
def preskladneni_seznam():
    # admin a skladník Pardubice → všechny v_tranzitu
    if current_user.role == "admin" or current_user.sklad == "Pardubice":
        transfers = Transfer.query.filter_by(status="v_tranzitu").order_by(Transfer.created_at.desc()).all()
    else:
        # ostatní skladníci vidí jen ty, které míří k nim
        transfers = Transfer.query.filter_by(
            status="v_tranzitu",
            target_sklad=current_user.sklad
        ).order_by(Transfer.created_at.desc()).all()

    return render_template(
        "preskladneni_seznam.html",
        transfers=transfers
    )


@app.route("/preskladneni_archiv")
@login_required
def preskladneni_archiv():
    # admin NEBO uživatel s přiděleným skladem Pardubice
    if current_user.role == "admin" or current_user.sklad == "Pardubice":
        archiv = (
            Transfer.query.order_by(Transfer.id.desc())
            .all()
        )
    else:
        archiv = (
            Transfer.query.filter(
                (Transfer.source_sklad == current_user.sklad) # Změna z created_by
                | (Transfer.target_sklad == current_user.sklad)
            )
            .order_by(Transfer.id.desc())
            .all()
        )
    return render_template("preskladneni_archiv.html", archiv=archiv)

@app.route("/export/transfer/<int:transfer_id>")
@login_required
def export_transfer(transfer_id):
    transfer = Transfer.query.get_or_404(transfer_id)
    if not (
        current_user.role == "admin"
        or current_user.sklad == "Pardubice"
        or transfer.target_sklad == current_user.sklad
    ):
        flash("Nemáte oprávnění exportovat tento dokument.", "danger")
        return redirect(url_for("preskladneni_detail", transfer_id=transfer_id))

    polozky = TransferItem.query.filter_by(transfer_id=transfer_id).all()
    produkty = {p.id: p for p in Product.query.all()}
    podrobnosti = []
    for pol in polozky:
        prod = produkty[pol.product_id]
        label = f"{prod.name}-{prod.color or '-'}-{prod.back_solution or '-'}"
        size_display = "-" if prod.category in ["doplnky", "ostatni"] else (pol.size or "-")
        podrobnosti.append({
            "label":    label,
            "size":     size_display,
            "quantity": pol.quantity
        })

    html = render_template(
        "export_transfer.html",
        transfer=transfer,
        polozky=podrobnosti
    )
    pdf = HTML(string=html).write_pdf()

    resp = make_response(pdf)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = \
        f"attachment; filename=preskladneni_{transfer.id}.pdf"
    return resp


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
        "saty":     list(range(32, 56, 2)),
        "boty":     list(range(36, 43)),
        "doplnky":  [UNIVERSAL_SIZE],
        "ostatni":  [UNIVERSAL_SIZE]
    }

    produkty = Product.query.order_by(Product.name).all()
    products_by_category = {
        "saty": [], "boty": [], "doplnky": [], "ostatni": []
    }
    
    # Sjednocená logika pro všechny kategorie
    for p in produkty:
        qtys = {}
        for v in velikosti[p.category]:
            st = Stock.query.filter_by(
                product_id=p.id,
                sklad=sklad,
                size=v
            ).first()
            qtys[v] = st.quantity if st else 0
        
        # Pro doplňky a ostatní předáme do šablony přímo kvantitu, ne slovník
        if p.category in ["doplnky", "ostatni"]:
            products_by_category[p.category].append({
                "name":     p.name,
                "color":    p.color,
                "quantity": qtys.get(UNIVERSAL_SIZE, 0)
            })
        else:
             products_by_category[p.category].append({
                "name":  p.name,
                "color": p.color,
                "sizes": qtys,
                "back_solution": p.back_solution
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
        "doplnky": [UNIVERSAL_SIZE],
        "ostatni": [UNIVERSAL_SIZE],
    }

    if request.method == "POST":
        # POST logika zůstává beze změny
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
            
            # --- OPTIMALIZACE ZDE (pro náhled) ---
            all_stock_records = Stock.query.filter_by(sklad=sklad).all()
            stock_map = {(s.product_id, s.size): s.quantity for s in all_stock_records}
            
            for pid_str, sizes in inv.items():
                pid = int(pid_str)
                prod = Product.query.get(pid)
                for size_str, new_qty in sizes.items():
                    size = int(size_str)
                    old_qty = stock_map.get((pid, size), 0)
                    delta = new_qty - old_qty
                    
                    size_display = "-" if prod.category in ["doplnky", "ostatni"] else size
                    if delta:
                        diffs.append({
                            "label": prod.variant_label,
                            "size": size_display,
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
                    size = int(size_str)
                    st = Stock.query.filter_by(
                        product_id=pid, sklad=sklad, size=size
                    ).first()
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

    # --- OPTIMALIZACE ZDE (pro zobrazení formuláře) ---
    inv = session.get("inventura_data", {})
    produkty = Product.query.order_by(Product.name).all()
    
    # 1. Načteme všechny potřebné skladové zásoby najednou
    all_stock_records = Stock.query.filter_by(sklad=sklad).all()
    
    # 2. Vytvoříme slovník pro rychlé vyhledávání
    stock_map = {(s.product_id, s.size): s.quantity for s in all_stock_records}

    data_by_cat = {
        "saty": [], "boty": [], "doplnky": [], "ostatni": []
    }
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
            # 3. Místo dotazu do DB použijeme rychlé vyhledání ve slovníku
            old_qty = stock_map.get((p.id, v), 0)
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