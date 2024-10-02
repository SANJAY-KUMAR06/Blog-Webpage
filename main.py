from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask.cli import load_dotenv
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, ForeignKey
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
import smtplib

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_KEY')
ckeditor = CKEditor(app)
Bootstrap5(app)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(Users, user_id)


def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # If id is not 1 then return abort with 403 error
        if current_user.id != 1:
            return abort(403)
        # Otherwise continue with the route function
        return f(*args, **kwargs)

    return decorated_function


gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)


# CREATE DATABASE
class Base(DeclarativeBase):
    pass


app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
# Create Tables
class Users(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(250), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)

    # This will act like a List of BlogPost objects attached to each User.
    # The "author" refers to the author property in the BlogPost class.
    posts = relationship("BlogPost", back_populates="author")  # links to BlogPost table
    comments = relationship("Comment", back_populates="comment_author")  # links to Comments Table


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # the below author_id is the foreign key that refers to the users id in Users table
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))

    # Create reference to the User object. The "posts" refers to the posts property in the User class.
    author = relationship("Users", back_populates="posts")
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    comments = relationship("Comment", back_populates="post_comments")  # link to Comment Table


class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # user and Comment
    author_id: Mapped[str] = mapped_column(Integer, db.ForeignKey("users.id"))
    comment_author = relationship("Users", back_populates="comments")

    # BlogPost and Comment
    post_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("blog_posts.id"))
    post_comments = relationship("BlogPost", back_populates="comments")

    text: Mapped[str] = mapped_column(Text, nullable=False)


with app.app_context():
    db.create_all()


#  Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=['GET', 'POST'])
def register():
    register_from = RegisterForm()
    if register_from.validate_on_submit():
        result = db.session.execute(db.select(Users).where(Users.email == register_from.email.data))
        check_user = result.scalar()

        if check_user:
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))

        hash_and_salted_password = generate_password_hash(
            register_from.password.data,
            method='pbkdf2:sha256',
            salt_length=8
        )
        new_user = Users(
            email=register_from.email.data,
            password=hash_and_salted_password,
            name=register_from.name.data
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)  # This line will authenticate the user with Flask-Login
        return redirect(url_for('get_all_posts'))

    return render_template("register.html", form=register_from, current_user=current_user)


# Retrieve a user from the database based on their email.
@app.route('/login', methods=['GET', 'POST'])
def login():
    login_form = LoginForm()
    if login_form.validate_on_submit():
        result = db.session.execute(db.select(Users).where(Users.email == login_form.email.data))
        check_login_user = result.scalar()

        if check_login_user and check_password_hash(check_login_user.password, login_form.password.data):
            login_user(check_login_user)
            return redirect(url_for('get_all_posts'))
        elif not check_login_user:
            flash("That email does not exist, Do Register.")
            return redirect(url_for('register'))
        else:
            flash('Password incorrect, please try again.')
            return redirect(url_for('login'))

    return render_template("login.html", form=login_form, current_user=current_user)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts, current_user=current_user)


#  Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>", methods=['GET', 'POST'])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to Register or Login to Post a Comment")
            return redirect(url_for('login'))
        new_comment = Comment(
            text=comment_form.comment.data,
            post_comments=requested_post,
            comment_author=current_user
        )
        db.session.add(new_comment)
        db.session.commit()

    result = db.session.execute(db.select(Comment))
    comments = result.scalars().all()
    return render_template("post.html", post=requested_post, current_user=current_user, form=comment_form,
                           all_comments=comments)


#  a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, current_user=current_user)


#  decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, current_user=current_user)


#  decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html", current_user=current_user)


@app.route("/contact", methods=['GET', 'POST'])
def contact():
    if request.method == "POST":
        with smtplib.SMTP("smtp.gmail.com") as connection:
            connection.starttls()
            connection.login(os.environ.get('MY_EMAIL'), os.environ.get('MY_PASSWORD'))
            connection.sendmail(from_addr=request.form['email'], to_addrs=os.environ.get('MY_EMAIL'),
                                msg=f"Subject:Blog Contact Form\n\n Name: {request.form['name']}\n\n"
                                    f"Phone: {request.form['phone']}\n\n"
                                    f"Message: {request.form['message']}\n\n")
            flash("Mail sent,Will touch With You Soon..")
            return redirect(url_for('contact'))
    return render_template("contact.html", current_user=current_user)


if __name__ == "__main__":
    app.run(debug=False)
