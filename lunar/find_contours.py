# lunar/find_contours.py

import cv2
import numpy as np
import concurrent.futures
import gc
import glob

def adjust_clip(image, black=0):
    # Adjusts pixel values: sets all pixel values below `black` to 0
    table = np.concatenate((
        np.zeros(black, dtype="uint8"),
        np.arange(black, 256, dtype="uint8")
    ))
    return cv2.LUT(image, table)

def process_frame(frametext, frame, frame_height, black, minArea, maxArea, video_file):
    clipped = adjust_clip(frame, black=black)
    imgray = cv2.cvtColor(clipped, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(imgray, black, 255, cv2.THRESH_TOZERO)
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    results = []
    for c in contours:
        area = cv2.contourArea(c)
        if minArea <= area <= maxArea:
            M = cv2.moments(c)
            if M["m00"] != 0:
                cX = int(M["m10"] / M["m00"])
                cY = int(M["m01"] / M["m00"])
                cY_flipped = frame_height - cY

                mask = np.zeros(imgray.shape, np.uint8)
                cv2.drawContours(mask, [c], 0, 255, -1)
                min_val, max_val, _, _ = cv2.minMaxLoc(imgray, mask=mask)
                mean_val = cv2.mean(frame, mask=mask)

                results.append((frametext, cX, cY_flipped, area, min_val, max_val, mean_val[0], video_file))
    return results

def process_videos(video_files, black=110, minArea=1.5, maxArea=1000.0, brightnessThreshold=200, threads=2, outfile='output.tab'):
    cv2.setNumThreads(threads)
    writefile = open('contours_' + outfile, 'w')
    writefile.write("frame\tcX\tcY\tarea\tminI\tmaxI\tmeanI\tvideo\n")

    all_results = []  # List to keep results in memory
    cumulative_frame = 0
    
    for video_file in video_files:
        cap = cv2.VideoCapture(video_file)
        if not cap.isOpened():
            continue

        ret, frame = cap.read()
        if not ret:
            cap.release()
            continue

        frame_height = frame.shape[0]
        local_frame_number = 0

        max_tasks = threads * 2
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            future_to_frame = {}
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                average_brightness = cv2.mean(frame)[0]
                if average_brightness > brightnessThreshold:
                    local_frame_number += 1
                    cumulative_frame += 1
                    continue

                local_frame_number += 1
                cumulative_frame += 1

                if len(future_to_frame) >= max_tasks:
                    done, _ = concurrent.futures.wait(future_to_frame, return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in done:
                        frame_id = future_to_frame[future]
                        try:
                            results = future.result()
                            all_results.extend(results)  # Add results to in-memory list
                            for result in results:
                                writefile.write("\t".join(map(str, result)) + "\n")
                        except Exception as exc:
                            print(f"Frame {frame_id} generated an exception: {exc}")
                        del future_to_frame[future]

                future = executor.submit(process_frame, cumulative_frame, frame, frame_height, black, minArea, maxArea, video_file)
                future_to_frame[future] = cumulative_frame
                del frame
                gc.collect()

            for future in concurrent.futures.as_completed(future_to_frame):
                frame_id = future_to_frame[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                    for result in results:
                        writefile.write("\t".join(map(str, result)) + "\n")
                except Exception as exc:
                    print(f"Frame {frame_id} generated an exception: {exc}")

        cap.release()

    writefile.close()
    return all_results  # Return results to use immediately

def find_contours_from_videos(video_pattern, black=110, minArea=1.5, maxArea=1000.0, brightnessThreshold=200, threads=2, outfile='output.tab'):
    video_files = sorted(glob.glob(video_pattern))
    if not video_files:
        print(f"No videos found matching pattern: {video_pattern}")
        return
    process_videos(video_files, black, minArea, maxArea, brightnessThreshold, threads, outfile)

