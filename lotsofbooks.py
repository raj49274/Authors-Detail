from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from project_database import Base, Authors, Books

engine = create_engine('sqlite:///databasewithuser.db')
# Bind the engine to the metadata of the Base class so that the
# declaratives can be accessed through a DBSession instance
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
# A DBSession() instance establishes all conversations with the database
# and represents a "staging zone" for all the objects loaded into the
# database session object. Any change made against the objects in the
# session won't be persisted into the database until you call
# session.commit(). If you're not happy about the changes, you can
# revert all of them back to the last commit by calling
# session.rollback()
session = DBSession()

# Eric ries books
author1 = Authors(name = "Eric Ries")
session.add(author1)
session.commit()


book1 = Books(name = "The Lean Startup", description = "The Lean Startup is most", price = "$6.4", authors = author1)
session.add(book1)
session.commit()

book2 = Books(name="The Startup Way", description="Eric Ries reveals how entrepreneurial principles can be used by businesses of all kinds", price="$10", authors = author1)
session.add(book2)
session.commit()

print "its done"
