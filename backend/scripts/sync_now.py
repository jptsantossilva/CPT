from ..app.services import sync


def main():
    print("Running sync...")
    sync.sync_all()
    print("Done")


if __name__ == "__main__":
    main()
