from db import DatabaseManager
from game import SnakeApp


def main() -> None:
    database = DatabaseManager()
    database.init_schema()
    app = SnakeApp(database)
    app.run()


if __name__ == "__main__":
    main()

