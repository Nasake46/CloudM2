import azure.functions as func

from signalr_messages import HUB_NAME

signalr_bp = func.Blueprint()


@signalr_bp.function_name(name="Negotiate")
@signalr_bp.route(route="negotiate", auth_level=func.AuthLevel.ANONYMOUS, methods=["GET", "POST"])
@signalr_bp.generic_input_binding(
    arg_name="connectionInfo",
    type="signalRConnectionInfo",
    hubName=HUB_NAME,
    connectionStringSetting="AzureSignalRConnectionString",
)
def negotiate(req: func.HttpRequest, connectionInfo) -> func.HttpResponse:
    return func.HttpResponse(connectionInfo, mimetype="application/json")
