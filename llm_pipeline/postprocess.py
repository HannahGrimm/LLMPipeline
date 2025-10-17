# llm_pipeline/postprocess.py
def write_timefile(path, labels, timestamps):
    t0 = int(1000 * timestamps[0])
    times = [int(1000*t)-t0 for t in timestamps]
    diffs = [times[i+1]-times[i] for i in range(len(times)-1)]
    with open(path,"w") as f:
        f.write(str(labels) + "\n" + str(times) + "\n" + str(diffs))
