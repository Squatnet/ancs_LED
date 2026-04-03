extends Spatial
# Called when the node enters the scene tree for the first time.
var currentScene = ""
var mouseCap
func _ready():
# warning-ignore:return_value_discarded
	Loader.connect("on_scene_loaded",self,"scene_loaded")
# warning-ignore:return_value_discarded
	Loader.request_resource("test",get_instance_id(),true)
func _process(_delta):
	if Input.is_action_just_pressed("toggle_fullscreen"):
		OS.set_window_fullscreen(!OS.window_fullscreen)

func scene_loaded(scene):
	Logger.addLog("SceneManager","Got resource from loader "+str(scene),2)
	if scene.requester == get_instance_id():
		Logger.addLog("SceneManager","Requested by us! "+str(scene.props.id),2)
		currentScene = scene.props.id
		Logger.addLog("SceneManager","Requested Scene not found Instancing new")
		var newS = scene.loader.instance()
		newS.set_name(scene.props.id)
		if newS.has_method("setup"):
			newS.setup()
		add_child(newS,true)
		newS.raise()
	else:
		instance_from_id(scene.requester).scene_loaded(scene.loader,scene.props.id)

