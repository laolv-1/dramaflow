# 策划案生成模板

## 角色设定模板
```
姓名: {name}
年龄: {age}
性别: {gender}
身份: {occupation}
性格: {traits}
外貌: {appearance}
服装: {wardrobe}
背景故事: {backstory}
人物关系: {relationships}
```

## 场景设定模板
```
场景号: {scene_id}
场景标题: {slugline}  # 例：1. 外景 暴雨天桥 夜 全景
地点: {location}
时间: {time}  # day/night/rain/snow
天气: {weather}
氛围: {mood}  # dark/warm/tense/sad/joyful
关键道具: {props}
角色在场: {characters}
```

## 图片提示词模板（角色）
```
[Age]-year-old [Gender] [Race/Ethnicity] with [skin_tone] skin,
[eye_color] eyes, [hair_color] [hair_style] hair,
wearing [outfit_description],
[pose_and_expression],
[lighting_description],
[background_setting],
[camera_angle],
[style_tags]
```

## 图片提示词模板（场景）
```
[location_description],
[time_of_day] lighting,
[weather/atmosphere_details],
[key_props],
[style_tags]
```

## 视频生成提示词模板（运镜）
```
[scene_description],
[character_action],
[camera_movement],  # slow push-in, tracking shot, etc.
[time_effect],      # slow motion, real-time
[mood_atmosphere],
[quality_tags]
```

## TTS提示词模板
```
旁白:
  文本: {narration_text}
  声线: {voice_name}
  语速: {rate}
  音调: {pitch}

台词:
  角色: {character_name}
  文本: {dialogue_text}
  声线: {voice_name}
  语速: {rate}
  情绪标记: {parenthetical}
```
