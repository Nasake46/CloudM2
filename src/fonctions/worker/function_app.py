import azure.functions as func
import logging

app = func.FunctionApp()

@app.function_name(name="BlobUpload")
@app.blob_trigger(arg_name="myblob", path="doc-storage/{name}",
                               connection="dockstorage") 
def blob_upload(myblob: func.InputStream):
    logging.info(f"Version CI/CD => Python blob trigger function processed blob"
                f"Name: {myblob.name}"
                f"Blob Size: {myblob.length} bytes")
