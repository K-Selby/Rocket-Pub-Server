from app import create_app

app = create_app()

if __name__ == "__main__":
    # Development server for the Mac. 0.0.0.0 also allows devices on the
    # same home Wi-Fi to connect to the site using the Mac's local IP.
    app.run(host="0.0.0.0", port=8000, debug=True)
