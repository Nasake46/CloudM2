import azure.functions as func

from blob_upload import blob_upload_bp
from service_bus_dlq import dlq_bp
from service_bus_processor import service_bus_bp
from signalr_negotiate import signalr_bp

app = func.FunctionApp()

app.register_functions(blob_upload_bp)
app.register_functions(service_bus_bp)
app.register_functions(dlq_bp)
app.register_functions(signalr_bp)
