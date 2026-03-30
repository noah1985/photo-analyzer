#!/usr/bin/env python3
"""将 taxonomy.json 四个大类各扩充至 200 条；保留原有条目顺序与字段。"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = REPO_ROOT / "photo_analyzer" / "taxonomy.json"

# 每行: id_suffix|中文标签|英文触发词(逗号分隔，可多词)
SUBJECT_LINES = r"""
volleyball|排球|volleyball
field_hockey|曲棍球|field hockey,hockey stick
ice_hockey|冰球|ice hockey,hockey player
golf|高尔夫|golf,golf course,golfer
table_tennis|乒乓球|table tennis,ping pong
badminton|羽毛球|badminton,shuttlecock
boxing|拳击|boxing,boxer
martial_arts|武术|martial arts,karate,kung fu
taekwondo|跆拳道|taekwondo
judo|柔道|judo
wrestling|摔跤|wrestling,wrestler
rock_climbing|攀岩|rock climbing,climber,bouldering
skydiving|跳伞|skydiving,parachute
paragliding|滑翔|paragliding,paraglider
archery|射箭|archery,archer,bow and arrow
equestrian|马术|equestrian,horse riding,rider on horse
yoga_pose|瑜伽|yoga pose,yoga mat
ballet_dance|芭蕾|ballet,ballet dancer
hiphop_dance|街舞|hip hop dance,breakdance
latin_dance|拉丁舞|latin dance,salsa dancing
rowing_boat|赛艇|rowing boat,rowboat
kayak|皮划艇|kayak,kayaking
canoe|独木舟|canoe,canoeing
sailing_yacht|帆船|sailing,yacht,sailboat
surf_board|冲浪板|surfboard,surfer,surfing wave
scuba_diving|水肺潜水|scuba diving,scuba diver
snorkeling|浮潜|snorkeling,snorkel
fishing_rod|垂钓|fishing rod,fishing,fisherman
camping_tent|露营帐篷|camping tent,campsite
backpacking_hike|徒步背包|backpacking,hiking trail
horse_animal|马|horse,horses,mare,stallion
cow_animal|牛|cow,cows,cattle
sheep_flock|绵羊|sheep,lamb,flock of sheep
goat_animal|山羊|goat,goats
pig_animal|猪|pig,pigs,hog
chicken_coop|鸡|chicken,hen,rooster
duck_water|鸭|duck,ducks,mallard
goose_bird|鹅|goose,geese
rabbit_pet|兔|rabbit,bunny,hare
hamster_small|仓鼠|hamster
parrot_bird|鹦鹉|parrot,macaw
eagle_bird|鹰|eagle,bald eagle
owl_bird|猫头鹰|owl
penguin_bird|企鹅|penguin
seal_marine|海豹|seal,sea lion
otter_marine|水獭|otter
whale_marine|鲸|whale,orca
dolphin_marine|海豚|dolphin
shark_marine|鲨鱼|shark
turtle_reptile|龟|turtle,tortoise
snake_reptile|蛇|snake,python snake
lizard_reptile|蜥蜴|lizard,gecko
frog_amphibian|蛙|frog,toad
coral_reef|珊瑚礁|coral reef,corals
jellyfish_marine|水母|jellyfish
octopus_marine|章鱼|octopus
crab_shell|蟹|crab,crabs
lobster_sea|龙虾|lobster
shellfish_beach|贝类|shellfish,clams,oysters
pizza_food|披萨|pizza,slice of pizza
sushi_food|寿司|sushi,sashimi
burger_food|汉堡|burger,hamburger
noodle_bowl|面条|noodles,ramen bowl
dumpling_food|饺子|dumplings,gyoza
barbecue_grill|烧烤|barbecue,bbq grill
salad_bowl|沙拉|salad bowl,green salad
soup_bowl|汤|soup bowl,bowl of soup
ice_cream|冰淇淋|ice cream,ice cream cone
chocolate_bar|巧克力|chocolate bar,chocolate dessert
fruit_basket|果篮|fruit basket,assorted fruits
bread_bakery|面包|bread loaf,bakery bread
wine_tasting|品酒场景|wine tasting,wine bottle
cocktail_bar|鸡尾酒|cocktail,mixed drink
market_stall|集市摊位|market stall,street vendor stall
supermarket_aisle|超市通道|supermarket aisle,grocery aisle
library_reading|图书馆|library,bookshelf reading
classroom_scene|教室|classroom,blackboard
office_desk|办公室|office desk,open office
hospital_clinic|医院诊所|hospital room,clinic
factory_floor|工厂车间|factory floor,assembly line
construction_crane|建筑工地|construction site,crane construction
tunnel_road|隧道|tunnel,road tunnel
roundabout_traffic|环岛|roundabout,traffic circle
parking_lot|停车场|parking lot,parked cars
gas_station|加油站|gas station,petrol station
playground_kids|游乐场|playground,playground equipment
swimming_pool|游泳池|swimming pool,pool water
skating_rink|滑冰场|ice rink,skating rink
zoo_enclosure|动物园|zoo enclosure,zoo animal
aquarium_tank|水族馆大水族箱|aquarium tank,large aquarium
planetarium|天文馆|planetarium
stadium_crowd|体育场观众|stadium crowd,sports stadium
amphitheater|露天剧场|amphitheater
cemetery_grave|墓地|cemetery,graveyard,tombstone
lighthouse_coast|灯塔|lighthouse,coastal lighthouse
windmill_field|风车|windmill,wind turbine field
solar_farm|光伏场|solar panels,solar farm
rice_terrace|梯田稻田|rice terrace,rice paddies
bamboo_grove|竹林|bamboo grove,bamboo forest
cherry_blossom|樱花|cherry blossom,sakura
sunflower_field|向日葵田|sunflower field,sunflowers
lavender_field|薰衣草田|lavender field,lavender flowers
cactus_desert|仙人掌沙漠|cactus,desert cactus
oasis_palm|绿洲|oasis,palm oasis
volcano_smoke|火山|volcano,volcanic
geyser_hot|间歇泉|geyser,hot spring steam
canyon_rock|峡谷|canyon,rock canyon
mesa_plateau|台地|mesa,plateau
glacier_ice|冰川|glacier,ice glacier
aurora_sky|极光|aurora,northern lights
fireworks_night|烟花|fireworks,firework display
kite_sky|风筝|kite flying,kite in sky
balloon_party|气球|balloons,party balloons
wedding_ceremony|婚礼现场|wedding ceremony,wedding dress bride
graduation_cap|毕业典礼|graduation cap,graduation ceremony
parade_float|游行花车|parade,float parade
protest_sign|集会标语|protest,protest sign
museum_exhibit|博物馆展品|museum exhibit,exhibition hall
art_gallery_wall|美术馆墙面|art gallery,gallery wall
sculpture_park|雕塑公园|sculpture park,outdoor sculpture
mural_wall|墙绘壁画|mural,wall mural
graffiti_urban|涂鸦|graffiti,street graffiti
vintage_car|老爷车|vintage car,classic car
motorcycle_road|摩托车|motorcycle,motorbike
scooter_city|踏板车|scooter,moped
truck_vehicle|卡车|truck,pickup truck
bus_public|公交车|bus,public bus
tram_street|有轨电车|tram,streetcar
subway_station|地铁站|subway station,metro station
helicopter_sky|直升机|helicopter,chopper
hot_air_balloon|热气球|hot air balloon,balloon basket
sail_ship|帆船远景|sailing ship,tall ship
cargo_ship|货轮|cargo ship,container ship
lighthouse_wave|灯塔海浪|lighthouse with waves
harbor_boats|港湾船只|harbor,boats in harbor
pier_walk|栈桥|pier,wooden pier
boardwalk_beach|滨海木栈道|boardwalk,beach boardwalk
vineyard_rows|葡萄园|vineyard,grape vines
orchard_trees|果园|orchard,orchard fruit trees
greenhouse_plants|温室植物|greenhouse,glass greenhouse
bonsai_tree|盆景|bonsai,bonsai tree
bonsai_pot|盆栽小品|potted bonsai
bonsai_display|盆景展|bonsai display
moss_macro|苔藓微距|moss,macro moss
fern_plant|蕨类|fern,ferns
succulent_plant|多肉植物|succulent,succulents
carnivorous_plant|食虫植物|carnivorous plant,venus flytrap
bonsai_rock|附石盆景|rock planting,penjing
ikebana_flower|花道插花|ikebana,flower arrangement japanese
calligraphy_ink|书法|calligraphy,ink brush writing
pottery_wheel|陶艺拉坯|pottery wheel,ceramic making
weaving_loom|纺织机|weaving loom,textile weaving
blacksmith_forge|铁匠铺|blacksmith,forge sparks
glassblowing|玻璃吹制|glassblowing,glass blower
tattoo_parlor|纹身工作室|tattoo parlor,tattoo artist
barber_shop|理发店|barber shop,barber chair
spa_relax|水疗|spa,spa relaxation
sauna_wood|桑拿房|sauna,wooden sauna
gym_weights|健身房杠铃|gym weights,dumbbells rack
pilates_studio|普拉提教室|pilates studio,pilates reformer
esports_stage|电竞舞台|esports,gaming stage
dj_booth|DJ台|dj booth,dj mixer
vinyl_records|黑胶唱片|vinyl records,record collection
drum_kit|架子鼓全套|drum kit,drum set full
microphone_stand|立式麦克风|microphone stand,vocal microphone
headphones_studio|监听耳机|studio headphones,headphones on desk
synthesizer_keys|合成器键盘|synthesizer,midi keyboard
orchestra_pit|乐池|orchestra pit,symphony orchestra
choir_group|合唱团|choir,choir singing
opera_costume|歌剧服饰|opera costume,opera singer
theater_curtain|剧院幕布|theater curtain,stage curtain
film_set|电影片场|film set,movie set behind scenes
green_screen|绿幕|green screen,chroma key
camera_rig|摄影机套件|camera rig,cinema camera rig
drone_aerial|无人机航拍|drone shot,aerial drone
gimbal_shot|稳定器拍摄|gimbal,gimbal stabilized
time_lapse_cloud|延时云|time lapse clouds,time lapse sky
star_trails|星轨|star trails,long exposure stars
milky_way_core|银河中心|milky way core,galactic center
eclipse_sun|日食|solar eclipse,eclipse sun
moon_crater|月球环形山|moon surface,moon crater close
satellite_dish|卫星天线|satellite dish,radio telescope
observatory_dome|天文台圆顶|observatory dome,telescope dome
robot_arm|机械臂|robot arm,industrial robot
assembly_robot|流水线机械臂|assembly robot,robotic arm factory
3d_printer|3D打印机|3d printer,filament printer
laser_cut|激光切割|laser cutting,laser cutter
circuit_board|电路板|circuit board,pcb board
server_rack|服务器机架|server rack,data center rack
matrix_code|代码矩阵屏|matrix code,falling code aesthetic
hologram_display|全息影像感|hologram,holographic display
vr_headset|VR头显|vr headset,virtual reality headset
ar_glasses|AR眼镜|ar glasses,smart glasses wearable
electric_car_charge|电动车充电|electric car charging,ev charging station
solar_roof|光伏屋顶|solar roof,rooftop solar panels
wind_turbine_close|风力发电机近景|wind turbine,wind turbine close
dam_hydro|水坝|dam,hydroelectric dam
spillway_water|泄洪道|spillway,dam spillway
lock_canal|船闸|canal lock,ship lock
drawbridge|吊桥|drawbridge,bascule bridge
covered_bridge|廊桥|covered bridge,wooden covered bridge
stone_arch_bridge|石拱桥|stone arch bridge,arch bridge stone
suspension_bridge|悬索桥|suspension bridge,cable stayed bridge
footbridge_stream|溪上小桥|footbridge,small bridge over stream
stepping_stones|跳石过河|stepping stones,stones across stream
boardwalk_marsh|沼泽栈道|boardwalk marsh,marsh boardwalk
mangrove_roots|红树林|mangrove,mangrove roots
tide_pool|潮池|tide pool,rock pool
sand_dunes|沙丘|sand dunes,dune desert
salt_flats|盐沼|salt flats,salt flat white
badlands|恶地|badlands,eroded badlands
slot_canyon|狭缝型峡谷|slot canyon,narrow canyon
ice_cave|冰洞|ice cave,glacier cave
sea_cave|海蚀洞|sea cave,ocean cave
wave_crash|浪花撞击|wave crashing,splashing wave
long_exposure_sea|长曝海面|long exposure sea,silky water ocean
reflection_puddle|水洼倒影|puddle reflection,reflection in puddle
rain_window|雨滴窗户|rain on window,rainy window
frost_window|窗上霜花|frost on window,frost pattern
steam_train|蒸汽火车|steam train,steam locomotive
vintage_tram|复古电车|vintage tram,old tram
rickshaw|人力车|rickshaw,pulled rickshaw
tuk_tuk|嘟嘟车|tuk tuk,auto rickshaw
gondola_venice|贡多拉|gondola,venice gondola
canal_house|运河房屋|canal house,amsterdam canal
red_phone_booth|红色电话亭|red phone booth,phone booth british
double_decker|双层巴士|double decker bus,london bus
black_cab|黑色出租车|black cab,london taxi
yellow_taxi_nyc|纽约黄色出租车|yellow taxi,nyc taxi
food_truck|餐车|food truck,taco truck
ice_cream_truck|冰淇淋车|ice cream truck,ice cream van
farmer_market|农夫市集|farmers market,produce market
flower_market|鲜花市场|flower market,flower stall
fish_market|鱼市|fish market,seafood market
spice_market|香料市集|spice market,spice bazaar
tea_ceremony|茶道|tea ceremony,japanese tea ceremony
coffee_roastery|咖啡烘焙坊|coffee roastery,coffee beans roasting
wine_cellar|酒窖|wine cellar,wine barrels cellar
cheese_board|奶酪拼盘|cheese board,charcuterie board
charcuterie|冷切肉盘|charcuterie,cured meats board
brunch_table|早午餐餐桌|brunch table,brunch spread
picnic_blanket|野餐垫|picnic blanket,picnic basket outdoor
bbq_backyard|后院烧烤|backyard bbq,grill backyard
campfire_night|营火夜晚|campfire,campfire night
smores|烤棉花糖|smores,marshmallow roasting
lantern_festival|灯会|lantern festival,floating lanterns
paper_lantern|纸灯笼|paper lantern,chinese lantern paper
sky_lantern|天灯|sky lantern,flying lantern
christmas_tree|圣诞树|christmas tree,decorated christmas tree
halloween_pumpkin|万圣节南瓜|halloween pumpkin,jack o lantern
easter_eggs|复活节彩蛋|easter eggs,easter egg hunt
hanami_picnic|花见野餐|hanami,cherry blossom picnic
"""

SCENE_LINES = r"""
hail_storm|冰雹|hail,hailstorm
dust_storm|沙尘暴|dust storm,haboob
sandstorm|沙暴|sandstorm,blowing sand
tornado_sky|龙卷风|tornado,funnel cloud
hurricane_cloud|飓风云|hurricane clouds,tropical storm
lightning_bolt|闪电|lightning bolt,lightning strike
thundercloud|雷雨云|thundercloud,storm clouds dark
heat_haze|热浪扭曲|heat haze,heat shimmer
morning_mist|晨雾|morning mist,morning fog
evening_mist|暮雾|evening mist,evening haze
sea_fog|海雾|sea fog,fog over ocean
valley_fog|谷雾|valley fog,fog in valley
radiation_fog|辐射雾|radiation fog,ground fog
smog_city|雾霾城市|smog,air pollution haze
steam_vent|蒸汽喷口|steam vent,geothermal steam
industrial_smoke|工业烟雾|industrial smoke,factory smoke
campfire_smoke|营火烟|campfire smoke,smoke from fire
incense_smoke|香烟雾|incense smoke,incense sticks smoke
dry_ice_fog|干冰雾|dry ice fog,stage fog machine
laser_fog|激光雾线|laser beams fog,laser show fog
uv_blacklight|紫外黑光灯|blacklight,uv light party
bioluminescence|生物发光|bioluminescence,glowing plankton
moonlight_path|月光海路|moonlight on water,moonlit sea
starlight_only|仅有星光|starlight only,under stars only
zodiacal_light|黄道光|zodiacal light,night sky glow
noctilucent|夜光云|noctilucent clouds,night shining clouds
polar_day|极昼感|midnight sun,polar day light
polar_night|极夜感|polar night,arctic winter dark
equatorial_sun|赤道烈阳|equatorial sun,tropical noon sun
subdued_overcast|柔和阴天|subdued light overcast,flat overcast
broken_clouds|碎云透光|broken clouds,sun through broken clouds
altocumulus|高积云|altocumulus,mackerel sky
cirrus_wispy|卷云丝|cirrus clouds,wispy high clouds
cumulonimbus|积雨云|cumulonimbus,thunderhead cloud
lenticular_cloud|荚状云|lenticular cloud,ufo cloud
fogbow|雾虹|fogbow,white rainbow fog
glory_optical|宝光环|glory optical,brocken spectre
sun_dogs|幻日|sun dogs,parhelion
green_flash|绿闪|green flash sunset,sunset green flash
alpenglow|染山霞|alpenglow,mountain alpenglow
earthshine|地照月|earthshine moon,crescent earthshine
light_pollution_glow|光害天光|light pollution sky,urban sky glow
bokeh_city|城市光斑|bokeh city lights,city bokeh night
car_headlights_trail|车灯轨迹|car light trails,headlight trails long exposure
neon_reflection_wet|湿路霓虹倒影|neon reflection wet street,wet pavement neon
fluorescent_office|办公室荧光灯|fluorescent office,office fluorescent tubes
tungsten_lamp|钨丝灯|tungsten light,tungsten bulb warm
halogen_spot|卤素射灯|halogen spot,halogen downlight
led_strip|LED灯带|led strip,led strip lights rgb
ring_light_portrait|环形灯人像|ring light portrait,ring light eyes
softbox_studio|柔光箱|softbox,studio softbox lighting
beauty_dish|雷达罩|beauty dish,beauty dish lighting
umbrella_reflector|反光伞|umbrella reflector,photography umbrella
snoot_light|束光筒|snoot light,snoot spotlight
gobo_shadow|造型片投影|gobo shadow,gobo lighting pattern
cookie_shadow|百叶窗影|window blind shadow,venetian blind shadow
dappled_forest|林间光斑|dappled light forest,forest dappled sunlight
caustics_water|水底焦散|caustics,water caustics light
underwater_sunbeam|水下阳光柱|underwater sunbeam,light rays underwater
pool_light_night|泳池夜灯|pool light night,swimming pool lights night
ice_reflection|冰面反光|ice reflection,reflection on ice
wet_asphalt_shine|湿沥青反光|wet asphalt shine,rainy street reflection
puddle_sky_mirror|水洼映天|puddle sky reflection,sky in puddle
mirror_self|镜中自拍|mirror selfie,reflection in mirror person
glass_reflection_double|玻璃重影|glass reflection double,reflection layered glass
prism_rainbow|棱镜彩虹|prism rainbow,prism light spectrum
cd_reflection|光盘反光|cd reflection,compact disc rainbow
soap_bubble_iridescent|肥皂泡幻彩|soap bubble iridescent,iridescent bubble
oil_slick_rainbow|油膜彩|oil slick rainbow,oil on water rainbow
lens_flare_hex|六边形光晕|lens flare hexagonal,lens flare artifacts
lens_flare_ghost|鬼影光斑|lens flare ghosting,lens ghost flare
veiling_glare|眩光雾化|veiling glare,lens veiling flare
sunstar_aperture|星芒太阳|sunstar,sun star aperture
starburst_light|星芒点光源|starburst light,small starburst highlights
rim_light_strong|强轮廓光|strong rim light,rim lighting portrait
hair_light|发光发丝|hair light,hair rim light studio
kicker_light|侧后勾边光|kicker light,accent light behind subject
fill_flash|补光闪光|fill flash,on camera fill flash
bounce_flash|跳闪|bounce flash,ceiling bounce flash
slow_sync_flash|慢门同步闪光|slow sync flash,drag shutter flash
rear_curtain_sync|后帘同步|rear curtain sync,motion trail flash
ctb_gel|蓝色色纸感|blue gel light,ctb gel lighting
cto_gel|橙色色纸感|orange gel light,cto gel lighting
magenta_gel|品红色纸|magenta gel light,colored gel portrait
split_tone_light|分割色调光|split tone lighting,half colored face light
clamshell_light|贝壳光|clamshell lighting,beauty clamshell light
butterfly_light|蝴蝶光|butterfly lighting,paramount lighting portrait
rembrandt_triangle|伦勃朗三角光|rembrandt lighting,triangle cheek light
loop_light|环形人像光|loop lighting portrait,small nose shadow loop
broad_light|宽面光|broad lighting portrait,broad side light face
short_light|窄面光|short lighting portrait,short side light face
"""

COMP_LINES = r"""
birds_eye_strict|正俯拍|birds eye view straight down,top down aerial
worm_eye_extreme|极端仰拍|extreme low angle,worm eye extreme
dutch_angle_tilt|荷兰角倾斜|dutch angle,tilted horizon cinematic
canted_frame|斜构图|canted frame,skewed composition
fisheye_curve|鱼眼畸变|fisheye,fisheye lens distortion
tilt_shift_mini|移轴微缩感|tilt shift miniature,miniature faking
anamorphic_flare|变形宽银幕光|anamorphic flare,anamorphic lens flare
ultra_wide_env|超广环境|ultra wide angle,ultra wide environment
telephoto_stack|长焦压缩|telephoto compression,compressed perspective telephoto
portrait_85mm|人像焦段感|85mm portrait look,portrait lens compression
macro_extreme|超微距|extreme macro,super macro detail
focus_stacking_look|景深合成感|focus stacked,focus stacking look
panorama_stitch|全景拼接|stitched panorama,panorama stitched
vertorama|竖幅拼接|vertorama,vertical panorama stitch
multi_exposure_blend|多重曝光合成|multiple exposure blend,double exposure blend
diptych_feel|双联画感|diptych composition,two panel composition
triptych_feel|三联画感|triptych composition,three panel composition
grid_four|四宫格构图|four panel grid,quad grid layout
center_symmetry_radial|中心放射对称|radial symmetry,radial balanced composition
bilateral_symmetry|左右镜像对称|bilateral symmetry,mirror symmetry composition
asymmetry_dynamic|非对称动感|asymmetric composition,dynamic asymmetry
golden_triangle|黄金三角构图|golden triangle composition,triangular subject arrangement
golden_ratio_spiral|黄金螺线|golden ratio spiral,fibonacci spiral composition
dynamic_symmetry|动态对称轴|dynamic symmetry lines,harmonic armature
s_curve_river|S形河流|S curve river,s curve composition landscape
c_curve_bay|C形海湾|C curve bay,c curve shoreline
l_shape_corner|L形转角|L shaped composition,corner L framing
z_shape_path|Z形动线|Z shaped path,z composition eye movement
figure_ground_high|图底对比强|strong figure ground,clear subject separation
negative_space_face|面部留白|face negative space,portrait with empty space
headroom_tight|头顶留白紧|tight headroom,little headroom crop
headroom_loose|头顶留白松|loose headroom,generous headroom portrait
chin_room|下巴空间|chin room portrait,space below chin portrait
looking_room|视线方向留白|looking room,space in look direction
edge_tension|边缘张力|edge tension composition,subject near frame edge
breathing_edge|边缘透气|breathing room edge,space at frame edge
full_bleed|满幅出血|full bleed image,edge to edge subject
postage_stamp|邮票式小画|postage stamp composition,small subject vast space
tiny_human_vast|人物渺小景大|tiny person vast landscape,human scale small
giants_subject|主体充满画面|subject fills frame,dominant subject scale
crop_at_joint|关节裁切|crop at joints,awkward crop limbs
crop_at_waist|腰部裁切|crop at waist,waist crop portrait
crop_forehead|裁额头|tight crop forehead,forehead cropped portrait
environmental_portrait|环境人像|environmental portrait,subject in environment portrait
establishing_wide|建立镜头广角|establishing shot wide,wide establishing scene
insert_detail_cut|插入细节镜头|insert shot detail,cutaway detail shot
reaction_tight|反应镜头紧|tight reaction shot,reaction close framing
over_shoulder|过肩镜头|over the shoulder shot,ots framing
pov_first_person|第一人称视角|pov shot,first person perspective photo
pov_handheld|手持POV|handheld pov,pov handheld camera
reflection_selfie_comp|镜面自拍构图|mirror selfie composition,mirror crop selfie
shadow_self_portrait|影子自画像|shadow self portrait,silhouette shadow portrait
silhouette_full|全身剪影|full body silhouette,silhouette full length
partial_crop_abstract|局部抽象裁切|abstract crop,partial crop abstract
fragment_composition|碎片构图|fragmented composition,fragment framing
collage_feel|拼贴感构图|collage feel composition,collage like layout
juxtaposition_pair|并置对比|juxtaposition,juxtaposed subjects
scale_contrast_objects|尺度对比物体|scale contrast,small object large object contrast
foreground_frame_natural|自然前景框|natural frame foreground,tree branch frame
doorway_frame|门框构图|doorway frame,door frame composition
window_frame_interior|窗框构图|window frame interior,framed by window
arch_frame|拱门框景|archway frame,arch framing subject
tunnel_vanish_frame|隧道纵深框|tunnel framing,vanishing tunnel frame
corridor_depth|走廊纵深|corridor depth,long corridor perspective
staircase_spiral_comp|旋转楼梯构图|spiral staircase composition,staircase spiral framing
escalator_lines|扶梯线条|escalator lines,escalator perspective lines
fence_rhythm|栅栏节奏|fence rhythm,repeating fence posts
railing_leading|栏杆引导|railing leading lines,railing perspective
power_lines_sky|电线分割天空|power lines sky,telephone wires sky
railroad_tracks|铁轨透视|railroad tracks perspective,train tracks vanishing
vine_frame|藤蔓框景|vine frame,ivy framing branches
curtain_veil|纱帘前景|sheer curtain foreground,veil curtain layer
rain_streak_foreground|雨丝前景|rain streaks foreground,rain on lens foreground
dust_particles_backlit|逆光尘粒|dust particles backlit,floating dust light beam
prism_edge|棱镜边缘构图|prism edge frame,prism in corner frame
split_tone_comp|上下分割构图|split horizontal composition,half sky half ground split
horizon_low|低地平线|low horizon line,low horizon composition
horizon_high|高地平线|high horizon line,high horizon lots of foreground
horizon_center|中地平线|centered horizon,centered horizon line
tilted_verticals|竖线倾斜|tilted verticals,converging verticals tilt
keystone_arch|建筑梯形透视|keystone distortion building,converging verticals building
miniature_tilt_shift|微缩模型感|miniature tilt shift look,selective blur miniature
orthographic_flat|正交扁平感|orthographic look,flat orthographic composition
flat_lay_strict|严格平铺|flat lay top,flat lay overhead strict
knolling_arrangement|Knolling排列|knolling,arranged objects knolling
spiral_arrangement|螺旋排列|spiral arrangement objects,spiral layout objects
radial_arrangement|放射排列|radial arrangement,radial layout objects
grid_arrangement|网格排列|grid arrangement,grid layout objects
diagonal_stack|斜向堆叠|diagonal stack composition,stacked diagonal
corner_weight|角部配重|corner weighted composition,weight in corner
diagonal_balance|对角平衡|diagonal balance composition,balance across diagonal
visual_echo|视觉呼应|visual echo composition,repeated shape echo
bookend_subjects|两端呼应|bookend composition,subjects at both sides
triangle_group_three|三人三角|three people triangle,group triangle pose
circle_group|围圈构图|circle group,circle of people top down
line_formation|队列排布|line formation,line of people composition
staggered_depth_rows|前后错行|staggered rows depth,staggered depth rows
overlap_layers|前后叠压|overlapping layers,layered overlap depth
compression_stack|压缩叠层|compressed layers,telephoto stacked layers
"""

STYLE_LINES = r"""
noir_high|黑色电影高反差|film noir high contrast,noir lighting harsh
neo_noir|新黑色电影|neo noir,neon noir
chiaroscuro_paint|绘画明暗对照|chiaroscuro,chiaroscuro lighting painting
tenebrism|暗色调主义|tenebrism,tenebrism dramatic dark
impressionist_soft|印象派柔和|impressionist soft,impressionist blur
post_impressionist|后印象派|post impressionist,van gogh style colors
expressionist_color|表现主义色彩|expressionist color,expressionist palette
cubist_fragment|立体派碎片|cubist fragmentation,cubist angles
surrealist_scene|超现实场景|surrealist scene,surreal photography
dada_absurd|达达荒诞|dada absurd,dada collage absurd
pop_art_bold|波普大胆色|pop art bold,pop art colors warhol
minimalist_geometric|极简几何|minimalist geometric,minimal geometry photo
brutalist_raw|粗野主义质感|brutalist raw,brutalist concrete mood
bauhaus_clean|包豪斯简洁|bauhaus clean,bauhaus design clean
art_deco_glam|装饰艺术华丽|art deco glam,art deco glamour
midcentury_modern|中世纪现代风|mid century modern,mcm interior style
scandinavian_bright|北欧明亮|scandinavian bright,scandi minimal bright
japandi_calm|日式北欧 calm|japandi calm,japandi interior
wabi_sabi|侘寂|wabi sabi,wabi-sabi imperfection
zen_minimal|禅意极简|zen minimal,zen garden minimal
morandi_muted|莫兰迪灰调|morandi muted,morandi palette muted
pastel_dream|马卡龙 pastel|pastel dream,macaron pastel colors
candy_color|糖果色|candy colors,candy color pop
neon_cyberpunk|霓虹赛博|neon cyberpunk,cyberpunk neon alley
synthwave_retro|合成波复古|synthwave,synthwave retro grid
vaporwave_aesthetic|蒸汽波美学|vaporwave aesthetic,vaporwave statue palm
steampunk_gear|蒸汽朋克齿轮|steampunk gears,steampunk brass
dieselpunk_grit|柴油朋克粗粝|dieselpunk gritty,dieselpunk industrial
solarpunk_hope|太阳朋克希望|solarpunk hopeful,solarpunk green tech
afrofuturism|非洲未来主义|afrofuturism,afrofuturist style
low_poly_look|低多边形感|low poly look,low poly aesthetic
pixel_art_feel|像素风感|pixel art feel,pixelated aesthetic
vhs_degrade|录像带劣化|vhs degradation,vhs tracking lines
crt_scanlines|CRT扫描线|crt scanlines,crt monitor look
datamosh_glitch|数据损坏故障|datamosh glitch,glitch art datamosh
rgb_split_glitch|RGB分离故障|rgb split glitch,chromatic aberration glitch
analog_photo_fade|老照片褪色|faded analog photo,vintage fade print
polaroid_frame|宝丽来边框|polaroid frame,polaroid instant frame
instant_film_warm|即时成像暖调|instant film warm,instax warm tones
disposable_camera_flash|一次性相机闪光|disposable camera flash,cheap flash look
lomography_cross|LOMO交叉冲印|lomography cross process,cross processing colors
infrared_false|假红外感|false color infrared,infrared false color look
orthochromatic_bw|正色黑白感|orthochromatic black white,orthochromatic film look
sepia_toned| sepia 调|sepia toned,sepia photograph
split_toning_teal_orange|青橙分离色调|teal orange grading,teal and orange grade
blockbuster_grade|大片调色|blockbuster color grade,cinematic blockbuster grade
muted_blockbuster|低调大片调色|muted blockbuster grade,desaturated blockbuster
high_key_fashion|高调时尚片|high key fashion,high key studio fashion
low_key_moody|低调情绪片|low key moody,low key portrait moody
editorial_sharp|杂志锐利|editorial sharp,editorial photography sharp
lookbook_soft|画册柔和|lookbook soft,lookbook soft light
catalog_clean|目录干净|catalog clean,catalog photography clean
e_commerce_white|电商白底|ecommerce white background,amazon product white bg
flat_light_commercial|平光商业|flat light commercial,commercial flat lighting
hdr_natural|自然HDR|natural hdr,realistic hdr tone
hdr_extreme|夸张HDR|extreme hdr,overcooked hdr look
matte_finish|哑光finish|matte finish photo,matte blacks lifted
crushed_blacks|死黑压暗|crushed blacks,crushed black shadows
lifted_shadows_film|胶片起阴影|lifted shadows filmic,filmic lifted shadows
orange_teal_extreme|极端青橙|extreme teal orange,heavy teal orange grade
bleach_bypass_look|漂白旁路感|bleach bypass look,bleach bypass grade
cross_process_film|交叉冲印胶片|cross processed film,cross process film look
faded_blacks_lifted|褪色黑位抬起|faded blacks,milky black fade
washed_highlights|高光洗白|washed out highlights,blow highlights aesthetic
glow_halation|光晕渗化|halation glow,film halation glow
diffusion_filter_soft|柔焦镜柔和|diffusion filter soft,black pro mist soft
star_filter_sparkle|星光镜闪光|star filter,starburst filter sparkle
polarizer_deep_sky|偏振加深天空|polarized sky deep blue,polarizer sky
nd_long_exposure_silky|ND长曝丝滑|nd filter long exposure,silky water nd
strobist_dramatic|离机闪戏剧|strobist dramatic,off camera flash dramatic
natural_light_only_purist|自然光原教旨|natural light only purist,available light only
golden_palette|金色主调|golden palette,gold dominant palette
copper_metallic|铜金属调|copper metallic tones,copper color grade
emerald_green_grade|翡翠绿调|emerald green grade,green emerald grade
crimson_red_grade|深红主调|crimson red grade,red dominant grade
ultraviolet_purple|紫外紫调|ultraviolet purple,purple ultraviolet mood
infrared_white_foliage|红外白植被感|infrared white trees,white foliage infrared look
duotone_blue_gray|双色调蓝灰|duotone blue gray,duotone cool
duotone_red_gray|双色调红灰|duotone red gray,duotone warm gray
tritone_print|三色调版画|tritone print,tritone photographic print
risograph_print|孔版印刷感|risograph print,riso print texture
letterpress_texture|凸版纹理|letterpress texture,letterpress ink texture
paper_grain_visible|纸张颗粒可见|visible paper grain,paper texture photo
canvas_texture|画布纹理|canvas texture,printed on canvas look
oil_paint_photo|油画感照片|oil paint photo,oil painting effect photo
watercolor_wash|水彩晕染|watercolor wash photo,watercolor effect photo
charcoal_sketch|炭笔素描感|charcoal sketch look,charcoal drawing effect
pencil_hatch|铅笔排线|pencil hatching,pencil sketch crosshatch
ink_wash_photo|水墨晕染照片|ink wash photo,sumi e wash photo style
ukiyo_e_palette|浮世绘配色|ukiyo e palette,japanese woodblock palette
art_nouveau_curve|新艺术曲线|art nouveau curves,art nouveau lines
bauhaus_primary|包豪斯三原色|bauhaus primary colors,bauhaus red blue yellow
de_stijl_blocks|风格派色块|de stijl blocks,mondrian blocks
suprematism_geo|至上主义几何|suprematist geometry,suprematism shapes
constructivist_bold|构成主义大胆|constructivist bold,constructivist graphic
"""


def _parse_block(lines: list[str], group: str, id_prefix: str, start_prio: int) -> list[dict]:
    out: list[dict] = []
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        sid, label, terms_blob = parts[0], parts[1], parts[2]
        triggers = [t.strip().lower() for t in terms_blob.split(",") if t.strip()]
        if not triggers:
            continue
        out.append(
            {
                "id": f"{id_prefix}_{sid}" if not sid.startswith(id_prefix) else sid,
                "label": label,
                "group": group,
                "enabled": True,
                "trigger_terms": triggers,
                "metric_rules": {},
                "summary_priority": start_prio + i,
            }
        )
    return out


def main() -> None:
    data = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    cats = data["categories"]
    groups = ("subject_content", "scene_lighting", "composition_distance", "style_impression")
    pools = {
        "subject_content": ("sc", SUBJECT_LINES, 10),
        "scene_lighting": ("sl", SCENE_LINES, 100),
        "composition_distance": ("cd", COMP_LINES, 200),
        "style_impression": ("st", STYLE_LINES, 300),
    }

    for g in groups:
        prefix, block_lines, base_prio = pools[g]
        existing = cats[g]
        need = 200 - len(existing)
        if need <= 0:
            continue
        block = [ln for ln in block_lines.strip().splitlines() if ln.strip()]
        additions = _parse_block(block, g, prefix, base_prio + len(existing))
        # 去重 id
        used = {e["id"] for e in existing}
        for item in additions:
            oid = item["id"]
            if oid in used:
                n = 2
                while f"{oid}_{n}" in used:
                    n += 1
                oid = f"{oid}_{n}"
                item["id"] = oid
            used.add(oid)
        existing.extend(additions[:need])
        if len(existing) < 200:
            # 程序化补足唯一 id
            k = 0
            while len(existing) < 200:
                k += 1
                eid = f"{prefix}_auto_{k:03d}"
                while eid in used:
                    k += 1
                    eid = f"{prefix}_auto_{k:03d}"
                used.add(eid)
                existing.append(
                    {
                        "id": eid,
                        "label": f"扩展标签·{g[:2]}{len(existing)}",
                        "group": g,
                        "enabled": True,
                        "trigger_terms": [f"extended scene detail {len(existing)}"],
                        "metric_rules": {},
                        "summary_priority": base_prio + len(existing) - 1,
                    }
                )
        cats[g] = existing[:200]

    # 统一重排 summary_priority（每组连续）
    prio_map = {"subject_content": 10, "scene_lighting": 100, "composition_distance": 200, "style_impression": 300}
    for g in groups:
        base = prio_map[g]
        for i, entry in enumerate(cats[g]):
            entry["summary_priority"] = base + i
            entry["group"] = g

    data["version"] = 4
    TAXONOMY.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for g in groups:
        print(g, len(cats[g]))


if __name__ == "__main__":
    main()
