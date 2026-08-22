import os

from app import create_app


app = create_app()


if __name__ == "__main__":
    debug_mode = os.environ.get("ROCKET_DEBUG", "0") == "1"

    if debug_mode:
        app.run(
            host="0.0.0.0",
            port=8000,
            debug=True,
        )
    else:
        from waitress import serve

        serve(
            app,
            host="0.0.0.0",
            port=8000,
            threads=8,
            channel_timeout=120,
        )
