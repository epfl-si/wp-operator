import json
import os
import mariadb


class classproperty:
    def __init__(self, func):
        self.fget = func
    def __get__(self, instance, owner):
        return self.fget(owner)


class MariaDB:
    __singleton = None

    @classmethod
    def __get(cls):
        if cls.__singleton is None:
            cls.__singleton = cls()

        return cls.__singleton

    def __init__(self, host, password):
        self._conn = self.connection(host, password)
        if self._conn:
            self._cursor = self._conn.cursor()

    @classproperty
    def cursor(cls):
        return cls.__get()._cursor

    @classproperty
    def conn(cls):
        return cls.__get()._conn

    def connection(self, host, password):
        try:
            return mariadb.connect(
                user="wp-fleet",
                password=password,
                host=host,
                port=3306,
                database="wp-fleet"
            )
        except mariadb.Error as e:
            print(f"Error connecting to MariaDB Platform: {e}")
            return None

    @classmethod
    def get_site(cls, query):
        try:
            cls.cursor.execute(query)
        except mariadb.Error as e:
            print(f"Error: {e}")

    @classmethod
    def close(cls):
        cls.conn.close()
