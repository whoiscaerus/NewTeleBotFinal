from backend.app.main import app

print("All registered routes:")
for route in app.routes:
    if hasattr(route, "path"):
        methods = getattr(route, "methods", ["Unknown"])
        print(f"{route.path} - {methods}")
