# Poipiku

<https://poipiku.com/>

## 配置

### POIPIKU_TOKEN

:material-lightbulb-on: 可选

浏览器已登录会话中的 `POIPIKU_LK` Cookie 值。

- **未配置 `POIPIKU_TOKEN` 时**：可直接抓取公开、ワンクッション（R-15/预警）以及普通年龄确认（R-18）投稿的公开展示图（`_640.jpg` JPEG 预览图）；仅登录可见、关注/X 限定、密码保护或需要 Poipass 年龄认证（R18+）的投稿需对应权限方可访问。
- **配置 `POIPIKU_TOKEN` 时**：
  - 通过详情接口获取原图（带签名的原格式 PNG/JPEG/GIF/WebP 链接）。
  - 支持抓取仅登录用户可见，以及当前账号有权限查看的关注者限定投稿。
  - 若检测到 `POIPIKU_TOKEN` 失效或过期会直接报错提醒。

## 自定义存储路径和文件名

更多信息请查阅 [自定义存储路径和文件名](./index.zh.md/#customizing-storage-path--file-name)。

### POIPIKU_FILE_PATH

:material-lightbulb-on: 可选，默认为 `Poipiku`

下载图片的存储路径。

### POIPIKU_FILE_NAME

:material-lightbulb-on: 可选，默认为 `{id}_{index} - {user[name]}({user[id]})`

下载图片的文件名。

### 可用变量

_此处只列出常用项。_

```json
{
  "id": "投稿 ID",
  "url": "投稿链接",
  "category": "投稿分类（如 できた、らくがき）",
  "description": "投稿文案描述",
  "tags": ["标签 1", "标签 2"],
  "user": {
    "id": "创作者用户 ID",
    "name": "创作者显示名称",
    "profile": "创作者简介",
    "avatar": "创作者头像链接",
    "url": "创作者主页链接",
    "posts_num": "投稿总数（ポイポイ）",
    "is_following": false
  },
  "original": "是否获取了原图（配置 POIPIKU_TOKEN 时为 true）",
  "filename": "原始文件名（不含扩展名与预览后缀）",
  "index": "图片序号（从 0 开始）",
  "extension": "文件扩展名（含前导点）"
}
```
