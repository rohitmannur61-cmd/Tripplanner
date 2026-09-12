"""
Project package init.
"""

try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass

