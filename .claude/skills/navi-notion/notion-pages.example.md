# Notion 落库位置（模板）

抄到 `$NAVI_HOME/notion-pages.md` 后填你自己的页面 ID。
页面 ID 从 Notion 页面 URL 末尾那串 32 位十六进制取，带不带连字符都行。

**建好集成后必须在目标页面 `···` → 连接 → 添加集成**，否则一律 `object_not_found`；
加在 `daily_root` 上，日期页与信息源子页会自动继承。

## 根页面

日期页都建在它下面。

```
daily_root = 00000000000000000000000000000000
```

## 信息源 → 子页名

日期页下的子页名，缺哪个就不写哪个源。

| skill | 子页名 |
|-------|--------|
| navi-arxiv | arxiv |
| navi-hfpapers | hfpaper |
| navi-zhihu | zhihu |
