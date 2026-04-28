import azure.functions as func

from blob_upload import blob_upload_bp
from service_bus_processor import service_bus_bp

app = func.FunctionApp()

app.register_functions(blob_upload_bp)
app.register_functions(service_bus_bp)
