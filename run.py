from app import create_app

app = create_app()

if __name__ == "__main__":
    # 0.0.0.0 allows other devices on the same local network to connect.
    # debug=True is useful while developing on your Mac.
    app.run(host="0.0.0.0", port=8000, debug=True)
