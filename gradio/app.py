from __future__ import annotations
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import posixpath
import pkg_resources
import traceback
from typing import Callable, Any, List, Optional, Tuple, TYPE_CHECKING
import uvicorn

from gradio import utils

STATIC_TEMPLATE_LIB = pkg_resources.resource_filename("gradio", "templates/")
STATIC_PATH_LIB = pkg_resources.resource_filename(
    "gradio", "templates/frontend/static")
VERSION_FILE = pkg_resources.resource_filename("gradio", "version.txt")
with open(VERSION_FILE) as version_file:
    version = version_file.read()
GRADIO_STATIC_ROOT = "https://gradio.s3-us-west-2.amazonaws.com/{}/static/".format(version)

app = FastAPI()
templates = Jinja2Templates(directory=STATIC_TEMPLATE_LIB)


###############
# Routes
###############


@app.head('/', response_class=HTMLResponse)
@app.get('/', response_class=HTMLResponse)
# @login_check # TODO
def main(request: Request):
    # session["state"] = None  # TODO
    return templates.TemplateResponse(
        "frontend/index.html", 
        {"request": request, "config": app.interface.config}
    )


@app.get("/static/{path:path}")
def static_resource(path: str):
    # if app.interface.share:
        # return redirect(GRADIO_STATIC_ROOT + path)
    # else:
    static_file = safe_join(STATIC_PATH_LIB, path)
    if static_file is not None:
        return FileResponse(static_file)
    raise HTTPException(status_code=404, detail="Static file not found")


@app.get("/config/")
def get_config():
    #if app.interface.auth is None or current_user.is_authenticated:
    return app.interface.config
    # else:
    #     return {"auth_required": True, "auth_message": app.interface.auth_message}


@app.post("/api/predict/")
# @login_check
async def predict(request: Request):
    body = await request.json()
    raw_input = body["data"]
    # Capture any errors made and pipe to the browser console
    if app.interface.show_error:
        try:
            prediction, durations = app.interface.process(raw_input)
        except BaseException as error:
            traceback.print_exc()
            return JSONResponse(content={"error": str(error)}, status_code=500)
    else:
        prediction, durations = app.interface.process(raw_input)
    avg_durations = []
    for i, duration in enumerate(durations):
        app.interface.predict_durations[i][0] += duration
        app.interface.predict_durations[i][1] += 1
        avg_durations.append(app.interface.predict_durations[i][0] 
            / app.interface.predict_durations[i][1])
    app.interface.config["avg_durations"] = avg_durations
    output = {"data": prediction, "durations": durations, 
              "avg_durations": avg_durations}
    # if app.interface.allow_flagging == "auto":
    #     flag_index = app.interface.flagging_callback.flag(
    #         app.interface, raw_input, prediction,
    #         flag_option=(None if app.interface.flagging_options is None else ""), 
    #         username=current_user.id if current_user.is_authenticated else None)
    #     output["flag_index"] = flag_index
    return output


@app.post("/api/flag/")
#@login_check
async def flag(request: Request):
    if app.interface.analytics_enabled:
        utils.log_feature_analytics(app.interface.ip_address, 'flag')
    body = await request.json()
    data = body['data']
    app.interface.flagging_callback.flag(
        app.interface, data['input_data'], data['output_data'], 
        data.get("flag_option"), data.get("flag_index"),
        None)
        # current_user.id if current_user.is_authenticated else None)
    return {'success': True}


@app.post("/api/interpret/")
#@login_check
async def interpret(request: Request):
    if app.interface.analytics_enabled:
        utils.log_feature_analytics(app.interface.ip_address, 'interpret')
    body = await request.json()
    raw_input = body["data"]
    interpretation_scores, alternative_outputs = app.interface.interpret(
        raw_input)
    return {
        "interpretation_scores": interpretation_scores,
        "alternative_outputs": alternative_outputs
    }



########
# Helper functions
########


def safe_join(directory: str, path: str) -> Optional[str]:
    """Safely path to a base directory to avoid escaping the base directory.
    Borrowed from: werkzeug.security.safe_join"""
    _os_alt_seps: List[str] = list(
        sep for sep in [os.path.sep, os.path.altsep] if sep is not None and sep != "/"
    )

    if path != "":
        filename = posixpath.normpath(path)

    if (
        any(sep in filename for sep in _os_alt_seps)
        or os.path.isabs(filename)
        or filename == ".."
        or filename.startswith("../")
    ):
        return None

    return posixpath.join(directory, filename)    
    
if __name__ == '__main__': # Run directly for debugging: python app.py
    from gradio import Interface    
    app.interface = Interface(lambda x: "Hello, " + x, "text", "text",
                              analytics_enabled=False)
    app.interface.config = app.interface.get_config_file()
    app.interface.show_error = True
    app.interface.flagging_callback.setup(app.interface.flagging_dir)
    uvicorn.run(app)