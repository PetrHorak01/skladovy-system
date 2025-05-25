from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, IntegerField, SelectField
from wtforms.validators import DataRequired, NumberRange
from wtforms import HiddenField, BooleanField

class LoginForm(FlaskForm):
    username    = StringField('Uživatelské jméno', validators=[DataRequired()])
    password    = PasswordField('Heslo', validators=[DataRequired()])
    remember_me = BooleanField('Pamatovat si mě')  # ← toto přidá
    submit      = SubmitField('Přihlásit')

class AddProductForm(FlaskForm):
    name = StringField('Název produktu', validators=[DataRequired()])
    category = HiddenField()  # Kategorie se nepřepisuje při editaci
    color = StringField('Barva')
    back_solution = StringField('Řešení zad')
    submit = SubmitField('Přidat produkt')


class StockForm(FlaskForm):
    product_id = SelectField("Produkt", coerce=int, validators=[DataRequired()])
    size = SelectField("Velikost", coerce=int)
    quantity = IntegerField("Počet kusů", validators=[DataRequired(), NumberRange(min=1)])
    sklad = SelectField("Sklad", choices=[
        ("Praha", "Praha"),
        ("Brno", "Brno"),
        ("Pardubice", "Pardubice"),
        ("Ostrava", "Ostrava")
    ], validators=[DataRequired()])
    submit = SubmitField("Naskladnit")


class UserForm(FlaskForm):
    username = StringField(
        'Uživatelské jméno',
        validators=[DataRequired()]
    )
    password = PasswordField(
        'Heslo',
        validators=[DataRequired()]
    )
    role = SelectField(
        'Role',
        choices=[('admin', 'Admin'), ('skladnik', 'Skladník')],
        validators=[DataRequired()]
    )
    sklad = SelectField(
        'Sklad (pro skladníka)',
        choices=[
            ('Praha', 'Praha'),
            ('Brno', 'Brno'),
            ('Pardubice', 'Pardubice'),
            ('Ostrava', 'Ostrava')
        ],
        validators=[DataRequired()]
    )
    submit = SubmitField('Přidat uživatele')

    
class SalesForm(FlaskForm):
    user_id = SelectField('Uživatel', coerce=int, validators=[DataRequired()])
    try_count = IntegerField('Počet zkoušek', validators=[DataRequired()])
    success_count = IntegerField('Počet prodejů', validators=[DataRequired()])
    submit = SubmitField('Uložit')


class NaskladnitForm(FlaskForm):
    sklad      = SelectField('Sklad', choices=[], validators=[DataRequired()])
    product_id = SelectField('Produkt', coerce=int, choices=[], validators=[DataRequired()])
    size       = SelectField('Velikost', coerce=str, choices=[])
    quantity   = IntegerField('Počet', validators=[DataRequired(), NumberRange(min=0)])
    submit     = SubmitField('Naskladnit')

class VyskladnitForm(FlaskForm):
    sklad      = SelectField('Sklad', choices=[], validators=[DataRequired()])
    product_id = SelectField('Produkt', coerce=int, choices=[], validators=[DataRequired()])
    size       = SelectField('Velikost', coerce=str, choices=[])
    quantity   = IntegerField('Počet', validators=[DataRequired(), NumberRange(min=0)])
    submit     = SubmitField('Vyskladnit')