extends Node

var thread # empty thread for later
export var scene_queue = {} # queued scenes
export var knownScenes = {} # scenes we can load (populated by chkDirs)
var file = File.new() # new File loader
export var cache = {} # loaded scenes go here
var awaiters = [] # scenes with a rush on
var LOGGING_ENABLED = true # logging on / off

## signals ##
# warning-ignore:unused_signal
signal on_progress
# warning-ignore:unused_signal
signal on_scene_loaded

# warning-ignore:unused_signal
signal load_started


func _ready():
	writeLog("Ready")
	thread = Thread.new() # create a new thread
	thread.start(self, "_thread_runner", null) # start it and make it run thread_runner()
	chkDirs() ## run chkdirs

func request_resource(id,requester,ret=true,props = null): 
# requests a resource, if you want a scene, use this Loader.request_resource("MainMenu",get_instance_id,Properties = {}, BLOCKING MODE = true)
	writeLog("Request resource "+id)
	if props == null: # good, its a hassle
		props = {}
	if !props.has("id"):
		# make it defo track its own ID, or it gets lost #
		props["id"] = id
	if !knownScenes[id]:
		# Unknown scene ID #
		writeLog("Resource "+id+" not found","Warn")
		return 404
	else:
		# Attempt to load #
		writeLog("Loading resource "+id)
		load_scene(knownScenes[id],requester,props,ret)
		return 200
func _thread_runner(_o):
# The thread runner (the complex bit, i dont even really understand it *cocaine code* ) #
	while true: # just run forever
		OS.delay_msec(5) # wait 5 ms
		
		if scene_queue.size() > 0: # if there are scenes in the queue
			for i in scene_queue: # iterate through the queue
				var err = scene_queue[i].loader.poll() # check the loading status of each item in the queue
				call_deferred("emit_signal", "on_progress", scene_queue[i].path, scene_queue[i].loader.get_stage_count(), scene_queue[i].loader.get_stage()) # emit the progess signal
				
				if err == ERR_FILE_EOF: # if we reach the end of file
					scene_queue[i].loader = scene_queue[i].loader.get_resource() # replace our loader with the actual "packedScene" rescource
					scene_queue[i].instance = scene_queue[i].loader.instance() # which we can then get an instance of
					cache[scene_queue[i].path] = scene_queue[i] # add the newly loaded resource to the cache
					if scene_queue[i].ret: # if we are meant to be fast loading 
						call_deferred("emit_signal", "on_scene_loaded", scene_queue[i]) # tell whoever gives a fuck that the load has finished
					scene_queue.erase(scene_queue[i].path) # remove the scene from the queue (it's done)
				elif err != OK: # if the error is not OK 
					writeLog("Failed to load: " + scene_queue[i].path,"Error") 
					scene_queue.erase(scene_queue[i].path) # just fuck it off
		
		for awaiter in awaiters: # check those awaiting jobs 
			if cache.has(awaiter.path): # if the awaited scene now exists is the cache
				if awaiter.path == cache[awaiter.path].path: # assign the awaiter its path 
					awaiter.loader = cache[awaiter.path].loader # and its loader
					awaiter.instance = cache[awaiter.path].instance.duplicate() # duplicate the instance we just made (as it's quicker and it's unlikely to be used)
					if awaiter.ret: # this is always true but haveing this check makes the code pretty much exactly ther same as for cache
						call_deferred("emit_signal", "on_scene_loaded", awaiter) # tell the awaiter about the loaded scene
					awaiters.remove(awaiters.find(awaiter)) ## remove the awaiter as the node has been served

func load_scene(path,requestr, props = null, ret = true):
# the internal scene loading for request_resource (don't call this directly, use request_resource() #
	writeLog("Load resource "+path)
	if !file.file_exists(path):
		# check the scene actually exists #
		writeLog("File does not exist: " + path,"Error")
		return # fail if it doesnt ( coz this means you've spelt the name wrong ie  request_resource("MianMenu",get_instance_id())
	if cache.has(path): 
		# the scene has already been loaded so load it from the cache #
		writeLog("Loading " + path + " From cache")
		writeLog(str(cache))
		
		if ret: # return the scene immediately
			call_deferred("emit_signal", "on_scene_loaded", { path = path,                 loader = cache[path].loader, requester = requestr, instance = cache[path].loader.instance(), props = props })
		# Call when idle / Emit singal / scene loaded   /   res://Scenes/MainMenu/MainMenu.tscn / PackedScene        /  id of request node   /             scene.instance()            /  Properties 
		
		return
	if !scene_queue.has(path):
		# Scene is not yet being loaded # 
		writeLog(path + " is not in queue, adding")
		scene_queue[path] = { path = path, loader = ResourceLoader.load_interactive(path), requester = requestr, instance = null, props = props, ret = ret }
#ADD TO QUEUE/res://Scenes/MainMenu/MainMenu.tscn / the resourceLoader we will be using  /  id of request node /     EMPTY       /   Properties / Return Immendiately
	else:
		# Scene is already being loaded, Putting a rush on"
		writeLog(path + " is in queue, Expediting")
		awaiters.push_back({ path = path, loader = null, requester = requestr, instance = null, props = props , ret = ret})
#Add to  Priority / Res://blah/blah.tscn / scene_queue has it / requesting node /   Empty    /    Properties  /  Return immeditely  
func is_loading_scene(path): 
# checks if a scene is loading # 
	writeLog("is loading "+path)
	return scene_queue.has(path) # returns true if the path exists in the queue

func clear_cache():
	# empties cache
	for item in cache:
		item.instance.queue_free()
	cache = {}

func chkDirs(): ## Checks directories and adds scenes to KnownScenes
	writeLog("Checking Dirs for Scenes!")
	var num = 0
	var dir = Directory.new() # Directory OBject 
	if dir.open("res://scenes/") == OK: # Check we can open Scenes
		dir.list_dir_begin() # Start listing dirs
		var file_name = dir.get_next() # get the file name
		while (file_name != ""): # run unless the filename is empty (end of list)
			#print(file_name)
			if file_name == ".." or file_name == ".": 
				# Skip the shortcut for "up a dir" and "this dir"
				pass
			else:
				# add a new scene to the list of knownScenes
				knownScenes[file_name] = "res://scenes/"+file_name+"/"+file_name+".tscn"
			if dir.current_is_dir(): # we are in a directory (not a file)
				num += 1
			file_name = dir.get_next() # get next dir
			
	else:
		writeLog("An error occurred when trying to access the path.","Error")
		# can't access dir (res://Scenes/ has been renamed
	writeLog("found "+str(num)+" dirs")
	num -= 2 # -2 for "." and ".."
	writeLog(knownScenes.keys()) # log all the dir names
	writeLog("total scenes = "+str(num))
	

func writeLog(message,lvl = "Info"):
	if lvl == "Error":
			Logger.addLog("Loader",str(message),0)
	if LOGGING_ENABLED:
		if lvl == "Info":
			Logger.addLog("Loader",str(message),2)
		elif lvl == "Warn":
			Logger.addLog("Loader",str(message),1)
