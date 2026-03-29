# B站 Web API - 接口参考

## 概述

B站大部分Web API为公开接口，无需API Key即可调用。
部分接口需要登录态Cookie才能获取完整数据（如会员弹幕、长评论等）。

**通用请求头**（建议携带，避免被风控）：
```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...
Referer: https://www.bilibili.com/
```

## 1. 视频信息接口

**URL**: `https://api.bilibili.com/x/web-interface/view`

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `bvid` | str | BV号（与aid二选一） |
| `aid` | int | av号（与bvid二选一） |

**返回关键字段**：

```json
{
  "code": 0,
  "data": {
    "aid": 170001,
    "bvid": "BV1xx411c7mD",
    "cid": 279786,
    "title": "视频标题",
    "desc": "视频简介",
    "duration": 360,
    "pubdate": 1709200000,
    "owner": {
      "mid": 12345678,
      "name": "UP主名称"
    },
    "stat": {
      "view": 1000000,
      "like": 50000,
      "coin": 20000,
      "favorite": 15000,
      "share": 3000,
      "danmaku": 8000,
      "reply": 5000
    },
    "pages": [
      {"cid": 279786, "page": 1, "part": "分P标题"}
    ]
  }
}
```

| 字段 | 说明 |
|------|------|
| `aid` | av号 |
| `bvid` | BV号 |
| `cid` | 视频cid（弹幕接口需要） |
| `duration` | 视频时长（秒） |
| `pubdate` | 发布时间（Unix时间戳） |
| `stat.view` | 播放量 |
| `stat.like` | 点赞数 |
| `stat.coin` | 投币数（用户消耗B币） |
| `stat.favorite` | 收藏数 |
| `stat.share` | 分享数 |
| `stat.danmaku` | 弹幕总数 |
| `stat.reply` | 评论数 |
| `pages` | 分P列表（每个分P有独立cid） |

## 2. 评论接口

### 主评论列表

**URL**: `https://api.bilibili.com/x/v2/reply`

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `type` | int | 评论区类型。1=视频, 12=专栏, 17=动态 |
| `oid` | int | 目标ID。视频评论用aid |
| `sort` | int | 0=按时间, 1=按点赞, 2=按回复数 |
| `pn` | int | 页码（从1开始） |
| `ps` | int | 每页条数（最大20） |
| `nohot` | int | 0=包含热评, 1=不包含 |

**返回关键字段**：

```json
{
  "code": 0,
  "data": {
    "page": {"count": 5000, "num": 1, "size": 20},
    "replies": [
      {
        "rpid": 123456789,
        "member": {
          "mid": "12345",
          "uname": "用户名",
          "level_info": {"current_level": 5}
        },
        "content": {"message": "评论正文"},
        "like": 2847,
        "rcount": 156,
        "ctime": 1709200000,
        "up_action": {"reply": false, "like": true}
      }
    ]
  }
}
```

| 字段 | 说明 |
|------|------|
| `rpid` | 评论唯一ID |
| `member.uname` | 用户昵称 |
| `member.level_info.current_level` | 用户B站等级(0-6) |
| `content.message` | 评论正文 |
| `like` | 点赞数 |
| `rcount` | 回复数（楼中楼） |
| `ctime` | 发布时间（Unix时间戳） |
| `up_action.reply` | UP主是否回复了该评论 |
| `up_action.like` | UP主是否给该评论点赞 |

### 楼中楼回复

**URL**: `https://api.bilibili.com/x/v2/reply/reply`

**参数**：

| 参数 | 说明 |
|------|------|
| `type` | 评论区类型（同上） |
| `oid` | 目标ID |
| `root` | 根评论rpid |
| `pn` | 页码 |
| `ps` | 每页条数（最大20） |

## 3. 弹幕接口

### XML弹幕接口（推荐，兼容性好）

**URL**: `https://api.bilibili.com/x/v1/dm/list.so`

**参数**：

| 参数 | 说明 |
|------|------|
| `oid` | 视频cid（注意：不是aid/bvid，是cid） |

**返回格式**：XML（可能经过deflate压缩）

每条弹幕格式：
```xml
<d p="进度,模式,字号,颜色,时间戳,弹幕池,用户hash,弹幕ID">弹幕文本</d>
```

**p属性各字段**：

| 位置 | 含义 | 说明 |
|------|------|------|
| 0 | progress | 弹幕出现时间（秒，可有小数） |
| 1 | mode | 弹幕模式：1/2/3=滚动, 4=底部, 5=顶部, 6=逆向, 7=精准定位, 8=高级 |
| 2 | fontsize | 字号：18=小, 25=标准, 36=大 |
| 3 | color | 颜色（十进制整数，如16777215=白色） |
| 4 | ctime | 发送时间（Unix时间戳） |
| 5 | pool | 弹幕池：0=普通, 1=字幕, 2=特殊 |
| 6 | user_hash | 用户hash（匿名化） |
| 7 | dmid | 弹幕唯一ID |

### Protobuf弹幕接口（新版，数据更全）

**URL**: `https://api.bilibili.com/x/v2/dm/web/seg.so`

**参数**：

| 参数 | 说明 |
|------|------|
| `type` | 1=视频 |
| `oid` | cid |
| `segment_index` | 分段序号（从1开始，每段6分钟） |

返回protobuf编码数据，需用`google.protobuf`解码。
脚本默认使用XML接口（更简单），如需protobuf接口请参考B站弹幕proto定义。

## 4. UP主视频列表

**URL**: `https://api.bilibili.com/x/space/wbi/arc/search`

**参数**：

| 参数 | 说明 |
|------|------|
| `mid` | UP主UID |
| `ps` | 每页条数（最大30） |
| `pn` | 页码 |
| `order` | 排序：pubdate=最新, click=最多播放, stow=最多收藏 |
| `keyword` | 搜索关键词（在该UP主视频中搜索） |

**注意**：此接口可能需要wbi签名（反爬机制），如遇403可尝试携带Cookie。

## 5. BV号 与 av号 互转

BV号是B站2020年引入的视频ID格式，与旧版av号一一对应。

- 通过视频信息接口可同时获取 `aid` 和 `bvid`
- 脚本支持任意格式输入，自动处理

## 6. 速率限制

| 情况 | 建议 |
|------|------|
| 无Cookie | 每次请求间隔 0.5-1秒 |
| 有Cookie | 每次请求间隔 0.3-0.5秒 |
| 触发412风控 | 暂停3-5秒后重试，或更换IP |
| 大规模采集 | 携带Cookie + 间隔1秒 + 限制单次采集量 |

**风控信号**：
- HTTP 412: 被风控拦截（最常见）
- 返回 `{"code": -412}`: 请求被拦截
- 返回 `{"code": -404}`: 视频不存在或已下架

## 7. 三连数据的分析基准（游戏区参考）

| 指标 | 优秀 | 正常 | 偏低 |
|------|------|------|------|
| 点赞率 (like/view) | >4% | 1-4% | <1% |
| 投币率 (coin/view) | >1% | 0.3-1% | <0.3% |
| 收藏率 (fav/view) | >2% | 0.5-2% | <0.5% |
| 投币/点赞比 | >40% | 15-40% | <15% |
| 收藏/点赞比 | >50% | 15-50% | <15% |

注意：以上为游戏区大致参考，不同品类和视频类型差异较大。
PV/预告片通常点赞率高但投币低；攻略/教程通常收藏率高但点赞低。
