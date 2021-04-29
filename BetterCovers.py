from glob import glob
from subprocess import call
from os import access, W_OK
from os.path import exists, realpath, join
import json
from sys import argv, exit
from datetime import timedelta
import time
from threading import Thread
from functions import *
from requests import post

config = {}
tasks = []


def generateTasks(metadata, path, type, title, overWrite, season = False, episode = False):
    conf = config[type]
    tsk = {
        'out': join(path, conf['output']) if type != 'episode' else path.rpartition('.')[0] + '.jpg',
        'type': type,
        'title': title,
        'season': season,
        'episode': episode,
        'overwrite': overWrite,
        'generateImage': path if type == 'episode' and config['episode']['generateImages'] else False}
    if 'mediainfo' in metadata:
        cfg = []
        if 'HDR' in metadata['mediainfo'] and 'UHD' in metadata['mediainfo'] and conf['mediainfo']['config']['UHD-HDR']:
            metadata['mediainfo'].remove('HDR')
            metadata['mediainfo'].remove('UHD')
            cfg.append('UHD-HDR')
        for mi in metadata['mediainfo']:
            if mi in conf['mediainfo']['config'] and conf['mediainfo']['config'][mi]: cfg.append(mi)
        if len(cfg) > 0:
            tsk['mediainfo'] = cfg
    
    if 'language' in metadata:
        for lg in conf['mediainfo']['audio'].split(','):
            if lg in metadata['language']:
                tsk['language'] = lg
                break

    if 'ratings' in metadata:
        cfg = {}
        for rt in metadata['ratings']:
            if conf['ratings']['config'][rt]: cfg[rt] = metadata['ratings'][rt]
        if len(cfg) > 0:
            tsk['ratings'] = cfg
    
    if 'certification' in metadata and conf['certifications']['config'][metadata['certification']]: 
        tsk['certification'] = metadata['certification']
    if 'cover' in metadata: 
        print(tsk['type'], metadata['cover'])
        tsk['image'] = metadata['cover']
    
    if overWrite or not exists(tsk['out']):
        if ('cover' in metadata or tsk['generateImage']) and ('mediainfo' in tsk or 'ratings' in tsk): tasks.append(tsk)
    else: log('Existing poster image found for: ' + title + (' S' + str(season) if season else '') + ('E' + str(episode) if episode else ''), 3, 3)

    tsk2 = tsk.copy()
    if 'backdrop' in metadata: tsk2['image'] = metadata['backdrop']
    tsk2['type'] = 'backdrop'
    tsk2['out'] = tsk2['out'].rpartition('/')[0] + '/' + config['backdrop']['output']
    
    if overWrite or not exists(tsk2['out']):
        if ('backdrop' in metadata or tsk2['generateImage']) and ('mediainfo' in tsk2 or 'ratings' in tsk2): tasks.append(tsk2)
    else: log('Existing backdrop image found for: ' + title + (' S' + str(season) if season else '') + ('E' + str(episode) if episode else ''), 3, 3)
    
    if type == 'tv' and 'seasons' in metadata:
        for season in metadata['seasons']:
            generateTasks(metadata['seasons'][season], metadata['seasons'][season]['path'], 'season', title, overWrite, season)
    
    if type == 'season' and 'episodes' in metadata:
        for episode in metadata['episodes']:
            generateTasks(metadata['episodes'][episode], metadata['episodes'][episode]['path'], 'episode', title, overWrite, season, episode)

def processFolder(folder):
    seasons = getSeasons(folder)
    type = 'tv' if len(seasons) > 0 else 'movie'
    name, year = getMediaName(folder)

    if type == 'movie' and not overWrite and exists(folder + '/' + config['movie']['output']) and exists(folder + '/' + config['backdrop']['output']):
        return log('Existing cover image found for: ' + name, 3, 3)
    
    st = time.time()

    metadata = getMetadata(name, type, year, config['omdbApi'], config['tmdbApi'])

    if type == 'tv':
        sns = getSeasonsMetadata(
            metadata['imdbid'] if 'imdbid' in metadata else False,
            metadata['tmdbid'] if 'tmdbid' in metadata else False,
            seasons,
            config['omdbApi'],
            config['tmdbApi'],
            getConfigEnabled(config['tv']['mediainfo']['config']) or getConfigEnabled(config['season']['mediainfo']['config']),
            minVotes,
            name,
            not exists(folder + '/' + config['tv']['output']) or not exists(folder + '/' + config['backdrop']['output']),
            overWrite)
        metadata['seasons'] = sns['seasons']   
        if 'mediainfo' in sns: metadata['mediainfo'] = sns['mediainfo'] 
    elif type == 'movie' and getConfigEnabled(config['movie']['mediainfo']['config']):
        mediaFiles = []
        for ex in extensions: 
            mediaFiles += glob(join(folder.translate({91: '[[]', 93: '[]]'}), '*.' + ex))
        
        mediaFiles = [fl for fl in mediaFiles if 'trailer' not in fl]
        if len(mediaFiles) > 0:
            minfo = getMediaInfo(mediaFiles[0])
            if minfo: 
                metadata['mediainfo'] = minfo['metadata']
                metadata['language'] = minfo['language']
            else: log('Error getting mediainfo for: ' + name, 1, 1)
        else: log('Error getting mediainfo no video files found on: ' + folder, 3, 1)
       
    generateTasks(metadata, folder, type, name, overWrite)
    log('Metadata and mediainfo found for: ' + name + ' in ' + str(timedelta(seconds=round(time.time() - st))), 2)

def processTask(task, thread, position, total):
    st = time.time()
    img = generateImage(
        config[task['type']],
        task['ratings'] if 'ratings' in task else False,
        task['certification'] if 'certification' in task else False,
        task['language'] if 'language' in task else False,
        task['mediainfo'] if 'mediainfo' in task else False,
        task['image'] if not task['generateImage'] else False,
        thread,
        coverHTML,
        task['out'],
        task['generateImage'])
    header = '[' + position.zfill(len(total)) + '/' + total + '][' + thread + '] '
    log(
        header + ('Succesfully generated image for: ' if img else 'Error generating image for: ') +
        task['title'] +
        ' (' + task['type'] + ')' +
        (' S' + str(task['season']) if task['season'] else '') +
        ('E' + str(task['episode']) if task['episode'] else '') +
        ' in ' +
        str(timedelta(seconds=round(time.time() - st))), 2 if img else 1)

def loadConfig(cfg):
    try:
        with open(cfg, 'r') as js:
            global config 
            config = json.load(js)
            if '-omdb' in argv and argv[argv.index('-omdb') + 1] != '': config['omdbApi'] = argv[argv.index('-omdb') + 1]
            if '-tmdb' in argv and argv[argv.index('-omdb') + 1] != '': config['tmdbApi'] = argv[argv.index('-tmdb') + 1]
        with open(cfg, 'w') as out: 
            out.write(json.dumps(config, indent = 5))
    except:
        log('Error loading config file from: ' + cfg, 1, 0)
        exit()

# region Params
overWrite = '-o' in argv and argv[argv.index('-o') + 1] == 'true'
threads = 20 if not '-w' in argv else int(argv[argv.index('-w') + 1])
config = {}
pt = argv[1]
cfg = './config.json' if '-c' not in argv else argv[argv.index('-c') + 1]
files = sorted(glob(pt)) if '*' in pt else [pt]
gstart = time.time()
if not exists(pt) and '*' in pt and len(glob(pt)) == 0:
    log('Media path doesnt exist', 1, 0)
    exit()
# endregion

# region Files
if not exists(cfg):
    log('Missing config.json, downloading default config.', 0, 3)
    if call(['wget', '-O', cfg, 'https://raw.githubusercontent.com/ilarramendi/Cover-Ratings/main/config.json', '-q']) == 0:
        log('Succesfully downloaded default config file', 2, 0)
        loadConfig(cfg)
    else: log('Error downloading default config file', 1, 0)
    exit()
    
loadConfig(cfg)
if config['tmdbApi'] == '' and config['omdbApi'] == '':
    log('A single api key is needed to work', 1, 0)
    exit() 

if exists(resource_path('cover.html')): 
    with open(resource_path('cover.html'), 'r') as fl: coverHTML = fl.read()
else:
    log('Missing cover.html', 1, 0)
    exit()
if not exists(resource_path('cover.css')):
    log('Missing cover.css', 1, 0)
    exit()

try:
    pt = sys._MEIPASS
except Exception: 
    pt = realpath(__file__).rpartition('/')[0]
# endregion

# region Check Dependencies
dependencies = [
    'mediainfo' if getConfigEnabled(config['tv']['mediainfo']['config']) or getConfigEnabled(config['season']['mediainfo']['config']) or getConfigEnabled(config['episode']['mediainfo']['config']) or getConfigEnabled(config['movie']['mediainfo']['config']) else False,
    'cutycapt',
    'ffmpeg' if config['episode']['generateImages'] else False]

for dp in [d for d in dependencies if d]:
    cl = getstatusoutput('apt-cache policy ' + dp)[1]
    if 'Installed: (none)' in cl:
        log(dp + ' is not installed', 1, 0)
        exit()
# endregion

log('DOWNLOADING METADATA AND GETTING MEDIAINFO FOR ' + str(len(files)) + ' FOLDERS')

# region Download Metadata
thrs = [False] * threads
for file in files:
    i = 0
    while True:
        if not (thrs[i] and thrs[i].is_alive()):
            thread = Thread(target=processFolder , args=(file, ))
            thread.start()
            thrs[i] = thread
            break
        i += 1
        if i == threads: i = 0

# Wait for threads to end
for th in thrs: 
    if th: th.join()
# endregion

log('GENERATING IMAGES FOR ' + str(len(tasks)) + ' ITEMS')

# region Start Threads
# Generating nedded files for threads
thrs = [False] * threads
thl = len(str(threads))
tskl = str(len(tasks))

if not exists(join(pt, 'threads')): call(['mkdir', join(pt, 'threads')])
for i in range(threads):
    pth = join(pt, 'threads', str(i).zfill(thl))
    if not exists(pth): call(['mkdir', pth])

j = 1
for tsk in tasks:
    i = 0
    while True:
        if not (thrs[i] and thrs[i].is_alive()):
            thread = Thread(target=processTask, args=(tsk, str(i).zfill(thl), str(j).zfill(len(tskl)), tskl))
            thread.start()
            thrs[i] = thread
            j += 1
            break
        i += 1
        if i == threads: i = 0

# Wait for threads to end
for th in thrs: 
    if th: th.join()
# endregion

call(['rm', '-r', join(pt, 'threads')])

post('https://emby.ilarramendi.com/Library/refresh?api_key=5f686d00249b4701a01515a0ccb0460c')
log('DONE! Total time was: ' + str(timedelta(seconds=round(time.time() - gstart))))
        
