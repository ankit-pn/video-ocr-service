import os
import time
import requests
import cv2
import pytesseract
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Timer
from concurrent.futures import Executor
import json
# Configuration
videos_directory = "/app/videos"
ocr_threads = int(os.getenv("OCR_THREADS", 4))
redis_api_password = os.getenv("REDIS_API_PASSWORD")
redis_api_domain = os.getenv("REDIS_API_DOMAIN")
notification_api_domain=os.getenv("NOTIFICATION_API_DOMAIN")

redis_get_url = f"https://{redis_api_domain}/get/"
redis_set_url = f"https://{redis_api_domain}/set/"
notify_url = f"http://host.docker.internal:8117/notify"
dbsize_url = f"https://{redis_api_domain}/dbsize/"

processed_videos_count = 0
total_videos_count = 0


class VideoHandler(FileSystemEventHandler):
    def __init__(self, executor):
        self.executor = executor

    def on_created(self, event):
        if event.is_directory:
            return
        # Extract file extension and check if it's an image file
        _, file_extension = os.path.splitext(event.src_path)
        if file_extension.lower() in ['.mp4']:
            self.executor.submit(process_video, event.src_path)
            update_total_videos_count()

def process_video(video_path):
    global processed_videos_count
    filename = os.path.basename(video_path)
    key = os.path.splitext(filename)[0]

    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    data = {
        "key": key,
        "db": 1,
        "password": redis_api_password
    }

    # Check if the video has already been processed
    response = requests.get(redis_get_url, headers=headers, json=data)
    if response.status_code == 200:
        # print(f"Video {filename} has already been processed.")
        return

    video = cv2.VideoCapture(video_path)
    fps = int(video.get(cv2.CAP_PROP_FPS))
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    concatenated_text = ""

    try:
        current_time = 0
        while current_time <= duration:
            video.set(cv2.CAP_PROP_POS_MSEC, current_time * 1000)
            ret, frame = video.read()
            if ret:
                pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                text = pytesseract.image_to_string(pil_image, lang='eng+hin')
                concatenated_text += text + " "
            current_time += 10  # Increase time by 10 seconds
        video.release()

        # Post concatenated OCR data to an API
        post_data = {
            "key": key,
            "value": concatenated_text.strip(),
            "db": 1,
            "password": redis_api_password
        }
        post_response = requests.post(redis_set_url, headers=headers, json=post_data)
        if post_response.status_code == 200:
            # print(f"OCR data for {filename} posted successfully.")
            processed_videos_count += 1
        else:
            print(f"Failed to post OCR data for {filename}: {post_response.text}")
    except Exception as e:
        print(f"Error processing {filename}: {e}")

def scan_directory(executor: Executor, path: str):
    global total_videos_count
    valid_extensions = ('.mp4')  # Define allowed image formats
    
    for root, dirs, files in os.walk(path, topdown=True):
        for name in files:
            if name.lower().endswith(valid_extensions):  # Check if the file is a valid image format
                file_path = os.path.join(root, name)
                executor.submit(process_video, file_path)
                total_videos_count += 1
            else:
                continue
               # print(f"Ignored non-image file: {name}")  # Optional: log ignored files

        for name in dirs:
            dir_path = os.path.join(root, name)
            if not os.access(dir_path, os.R_OK):
                print(f"Permission denied: {dir_path}")
                continue

def update_total_videos_count():
    global total_videos_count
    total_videos_count = sum([len(files) for r, d, files in os.walk(videos_directory)])

def send_notification():
    global processed_videos_count, total_videos_count
    try:
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        } 
        # Get total number of processed videos from the database
        response = requests.get(dbsize_url,headers=headers, json={"password": redis_api_password})
        if response.status_code == 200:
            total_processed_videos = response.json().get('dbsize', 0)
        else:
            total_processed_videos = 0

        # Notify API
        notify_data = {
            "processed_videos_count": processed_videos_count,
            "total_videos_count": total_videos_count,
            "total_processed_videos": total_processed_videos
        }
        notify_response = requests.post(notify_url, json=notify_data)
        if notify_response.status_code == 200:
            print("Notification sent successfully.")
        else:
            print(f"Failed to send notification: {notify_response.text}")

        # Reset the counter for the next hour
        processed_videos_count = 0
    except Exception as e:
        print(f"Error sending notification: {e}")

    # Schedule the next notification
    Timer(3600, send_notification).start()
    
if __name__ == "__main__":
    print("Processes has started")
    executor = ThreadPoolExecutor(max_workers=ocr_threads)

    # Initial scan of all directories and subdirectories
    scan_directory(executor, videos_directory)

    event_handler = VideoHandler(executor)
    observer = Observer()
    observer.schedule(event_handler, path=videos_directory, recursive=True)
    
    observer.start()
    print(f"Started monitoring {videos_directory} with {ocr_threads} threads.")

    # Update the total image count initially
    update_total_videos_count()

    # Start the notification timer
    Timer(3600, send_notification).start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
