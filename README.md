# S.T.A.L.K.E.R. X-Ray Engine — Vulkan + x64

Рабочий репозиторий модернизации X-Ray Engine для S.T.A.L.K.E.R.: Shadow of Chernobyl.

Текущий этап: RC6 — переход на x64 и Vulkan, при сохранении совместимого DX9 fallback.

Сборка движка x64/Vulkan проходит в GitHub Actions. Итоговый пользовательский комплект должен содержать не только `bin/`, но и полную `gamedata/` со всеми изменёнными игровыми ресурсами. Текущий канонический набор ресурсов — cumulative gamedata v24; его контрольные суммы и правила упаковки описаны в `resources/GAMEDATA_V24.md`.

Перед публикацией полного пакета используйте `tools/validate_rc6_release.py <каталог_релиза>`: проверка требует AMD64 `XR_3DA.exe`, `xrCore.dll`, `xrRender_VK.dll`, а также реальные каталоги `gamedata/config` и `gamedata/textures`.
