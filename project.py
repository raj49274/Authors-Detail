from flask import Flask, render_template, request, redirect
from flask import jsonify, url_for, flash
from sqlalchemy.orm import sessionmaker
from project_database import Base, Authors, Books, User
from sqlalchemy import create_engine, asc

from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests
from helperFunction import createUser, getUserInfo, getUserID, login_required


app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Authors Detail"


# Connect to Database and create database session
engine = create_engine('sqlite:///databasewithuser.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


# Create anti-forgery state token
@app.route('/login')
def showLogin():
    state = ''.join(
        random.choice(string.ascii_uppercase + string.digits)
        for x in range(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code, now compatible with Python3
    request.get_data()
    code = request.data.decode('utf-8')

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    # Submit request, parse response - Python3 compatible
    h = httplib2.Http()
    response = h.request(url, 'GET')[1]
    str_response = response.decode('utf-8')
    result = json.loads(str_response)

    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match g iven user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(
            json.dumps('Current user is already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    # see if user exists, if it doesn't make a new one
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' "style = "width: 300px; height: 300px ;border-radius: 150px"> '
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output


@app.route('/gdisconnect')
def gdisconnect():
    # Only disconnect a connected user.
    access_token = login_session.get('access_token')
    if access_token is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]

    if result['status'] == '200':
        # Reset the user's sesson.
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        flash("you are now successfully logged out")
        return redirect(url_for('showAuthors'))
    else:
        # For whatever reason, the given token was invalid.
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


# show all the names of authors
@app.route('/')
@app.route('/authors/')
def showAuthors():
    author1 = session.query(Authors).order_by(asc(Authors.name))
    if 'username' not in login_session:
        return render_template('publicAuthors.html', author1=author1)
    else:
        return render_template('authors.html', author1=author1)


# Adding authors names
@app.route('/authors/new/', methods=['GET', 'POST'])
@login_required
def newAuthor():
    if request.method == 'POST':
        newAuthor = Authors(
            name=request.form['name'], user_id=login_session['user_id'])
        session.add(newAuthor)
        flash('New Profile %s Successfully Created' % newAuthor.name)
        session.commit()
        return redirect(url_for('showAuthors'))
    else:
        return render_template('newAuthors.html')


# show all books
@app.route('/authors/<int:author_id>/')
@app.route('/authors/<int:author_id>/books/')
def showBooks(author_id):
    author = session.query(Authors).filter_by(id=author_id).one()
    creator = getUserInfo(author.user_id)
    book = session.query(Books).filter_by(author_id=author_id).all()
    if 'username' not in login_session\
            or creator.id != login_session['user_id']:
        return render_template(
            'publicbooks.html', author=author, books=book, creator=creator)
    else:
        return render_template(
            'books.html', author=author, books=book, creator=creator)


# creating new Books
@app.route('/authors/<int:author_id>/books/new/', methods=['GET', 'POST'])
@login_required
def newBooks(author_id):
    author = session.query(Authors).filter_by(id=author_id).one()
    if request.method == 'POST':
        newItem = Books(
            name=request.form['name'], price=request.form['price'],
            description=request.form['description'], author_id=author_id,
            user_id=login_session['user_id'])
        session.add(newItem)
        session.commit()
        flash('New Book %s Successfully Created' % (newItem.name))
        return redirect(url_for('showBooks', author_id=author_id))
    else:
        return render_template('newBook.html', author_id=author_id)


# delete a Authors
@app.route('/authors/<int:author_id>/delete/', methods=['GET', 'POST'])
@login_required
def deleteAuthor(author_id):
    authorToDelete = session.query(Authors).filter_by(id=author_id).one()
    creator = getUserInfo(authorToDelete.user_id)
    if creator.id != login_session['user_id']:
        flash('You are not authorised to delete this profile')
        return redirect(url_for('showAuthors'))
    if request.method == 'POST':
        session.delete(authorToDelete)
        flash('%s Successfully Deleted' % authorToDelete.name)
        session.commit()
        return redirect(url_for('showAuthors', author_id=author_id))
    else:
        return render_template('deleteAuthor.html', author=authorToDelete)


# Editing Authors
@app.route('/authors/<int:author_id>/edit/', methods=['GET', 'POST'])
@login_required
def editAuthor(author_id):
    editedAuthor = session.query(Authors).filter_by(id=author_id).one()
    creator = getUserInfo(editedAuthor.user_id)
    if creator.id != login_session['user_id']:
        flash('You are not authorised to edit this profile')
        return redirect(url_for('showAuthors'))
    if request.method == 'POST':
        if request.form['name']:
            editedAuthor.name = request.form['name']
            flash('Author detail Successfully Edited %s' % editedAuthor.name)
        return redirect(url_for('showAuthors'))
    else:
        return render_template('editAuthor.html', author=editedAuthor)


# Editing books
@app.route(
    '/authors/<int:author_id>/books/<int:book_id>/edit',
    methods=['GET', 'POST'])
@login_required
def editBooks(author_id, book_id):
    editbook = session.query(Books).filter_by(id=book_id).one()
    authorQuery = session.query(Authors).filter_by(id=author_id).one()
    creator = getUserInfo(authorQuery.user_id)
    if creator.id != login_session['user_id']:
        flash('You are not authorised to edit this book')
        return redirect(url_for('showAuthors'))
    if request.method == 'POST':
        if request.form['name']:
            editbook.name = request.form['name']
        if request.form['description']:
            editbook.description = request.form['description']
        if request.form['price']:
            editbook.price = request.form['price']
        session.add(editbook)
        session.commit()
        flash('Book Successfully Edited')
        return redirect(url_for('showBooks', author_id=author_id))
    else:
        return render_template(
            'editBook.html', author_id=author_id,
            book_id=book_id, item=editbook)


# delete a book
@app.route(
    '/authors/<int:author_id>/books/<int:book_id>/delete',
    methods=['GET', 'POST'])
@login_required
def deleteBooks(author_id, book_id):
    authorQuery = session.query(Authors).filter_by(id=author_id).one()
    itemToDelete = session.query(Books).filter_by(id=book_id).one()
    creator = getUserInfo(authorQuery.user_id)
    if creator.id != login_session['user_id']:
        flash('You are not authorised to delete this book')
        return redirect(url_for('showAuthors'))
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('Book Successfully Deleted')
        return redirect(url_for('showBooks', author_id=author_id))
    else:
        return render_template('deleteBook.html', item=itemToDelete)


# JSON APIs to view Restaurant Information
@app.route('/authors/JSON')
def authorsJSON():
    authors = session.query(Authors).all()
    return jsonify(authors=[r.serialize for r in authors])


@app.route('/authors/<int:author_id>/books/JSON')
def authorsBooksJSON(author_id):
    author = session.query(Authors).filter_by(id=author_id).one()
    book = session.query(Books).filter_by(
        author_id=author_id).all()
    return jsonify(Books=[i.serialize for i in book])


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
