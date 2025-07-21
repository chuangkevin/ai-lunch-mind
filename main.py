# 主程式入口

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
from modules.weather import get_weather_data


app = FastAPI()

# 掛載 frontend 靜態檔案到 /static


# 正確的靜態檔案掛載方式，加上 html=True
import pathlib
STATIC_DIR = str(pathlib.Path(__file__).parent / "frontend")
print(f"[DEBUG] FastAPI static mount: {STATIC_DIR}")
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")

# / 路徑自動回傳 static/index.html
@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# API 路由
@app.get("/weather")
def weather_endpoint(latitude: float = None, longitude: float = None, location: str = None):
    """
    天氣查詢 API 端點
    :param latitude: 緯度
    :param longitude: 經度
    :param location: 地名
    :return: 天氣資料
    """
    if latitude is not None and longitude is not None:
        return get_weather_data(latitude, longitude)
    # 可擴充：支援地名查詢
    return {"error": "請提供座標或城市名稱。"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
