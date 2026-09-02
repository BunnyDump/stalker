# Gamedata v24 — обязательный ресурсный пакет RC6

Итоговый пользовательский релиз X-Ray RC6 считается полным только при наличии двух каталогов в корне пакета:

- `bin/` — x64-бинарники движка, включая `XR_3DA.exe`, `xrCore.dll` и `xrRender_VK.dll`;
- `gamedata/` — полный кумулятивный набор изменённых игровых ресурсов.

Канонический ресурсный архив текущего этапа: `gamedata_modernized_fixed_v24.zip`.

SHA-256 полного архива:

`ce0bc0845f888c6cf879e56e4ccfc0d37008e0d641ca1b1f9c560dc944e08f27`

Дополнительный UI/FX delta-патч v24 имеет SHA-256:

`78c88450928091f3992122ed92d2a602561e8f48d0c185c1bcd50280fdae0859`

Полный архив v24 уже включает кумулятивные изменения предыдущих итераций и является источником для итоговой `gamedata`. Delta-патч не должен использоваться вместо полного архива при создании пользовательского релиза.

## Детерминированная подготовка релиза

Релиз необходимо собирать через `tools/stage_rc6_release.py`, а не ручным копированием. Скрипт:

- копирует полный каталог `bin/`;
- принимает полный каталог `gamedata` либо ZIP с ним;
- при `--expected-gamedata-sha256 v24` проверяет канонический SHA-256 архива v24;
- защищает распаковку от выхода ZIP-путей за каталог назначения;
- формирует `SHA256SUMS.txt` для всех файлов готового релиза;
- формирует `RC6_RELEASE_INFO.txt` с происхождением gamedata;
- автоматически запускает `tools/validate_rc6_release.py`.

Пример для канонического пакета v24:

```text
python tools/stage_rc6_release.py --bin <build-bin> --gamedata gamedata_modernized_fixed_v24.zip --expected-gamedata-sha256 v24 --output STALKER_RC6_RELEASE
```

Ожидаемая структура:

```text
S.T.A.L.K.E.R. RC6/
├── SHA256SUMS.txt
├── RC6_RELEASE_INFO.txt
├── bin/
│   ├── XR_3DA.exe
│   ├── xrCore.dll
│   ├── xrRender_VK.dll
│   └── ...
└── gamedata/
    ├── config/
    ├── textures/
    └── ...
```

Перед публикацией комплект необходимо проверить скриптом `tools/validate_rc6_release.py <каталог_релиза>`. Скрипт намеренно отклоняет engine-only пакет без `gamedata`.
