# 主程式入口
from fastapi import FastAPI
from modules.weather import get_weather_data

app = FastAPI()

@app.get("/weather")
def weather_endpoint(latitude: float, longitude: float):
    """
    天氣查詢 API 端點
    :param latitude: 緯度
    :param longitude: 經度
    :return: 天氣資料
    """
    return get_weather_data(latitude, longitude)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
