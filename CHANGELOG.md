# Changelog

## [0.7.1](https://github.com/LouisPauchet/open-csi-publisher/compare/open-csi-publisher-v0.7.0...open-csi-publisher-v0.7.1) (2026-08-14)


### Bug Fixes

* **loggernet:** handle mixed fractional/whole-second TOA5 timestamps ([f52ffd6](https://github.com/LouisPauchet/open-csi-publisher/commit/f52ffd641913366f93037eeb3b8126d35e284c8b))

## [0.7.0](https://github.com/LouisPauchet/open-csi-publisher/compare/open-csi-publisher-v0.6.0...open-csi-publisher-v0.7.0) (2026-08-09)


### Features

* **loggernet:** add cheap first-line-only TOA5 time-start parser ([0a75204](https://github.com/LouisPauchet/open-csi-publisher/commit/0a75204ea1fe68b755da2f56298bed52650ccaa0))
* **settings:** add dataset build timeout and max size env vars ([683af28](https://github.com/LouisPauchet/open-csi-publisher/commit/683af285b3e7a62534624a385488da0ed25e09cb))
* **web:** add a /visualize page for plotting dataset variables ([08a31a3](https://github.com/LouisPauchet/open-csi-publisher/commit/08a31a39398845d4ddd43bc639a1d3902fcafde1))
* **web:** add manual y-axis range control and shorter x-axis labels ([3940f06](https://github.com/LouisPauchet/open-csi-publisher/commit/3940f06355fa7d8c23c909636edb2e8ef6f25580))
* **web:** link to Visualize from the header nav and dataset panel ([b4ea678](https://github.com/LouisPauchet/open-csi-publisher/commit/b4ea67877ea9d295c4c177e50e3dce017a8b1d6d))
* **web:** make the visualize chart's axes interactive ([cfd22b8](https://github.com/LouisPauchet/open-csi-publisher/commit/cfd22b84a37880107e2b81afe6189b59f486ddd5))
* **web:** vendor Chart.js for the upcoming visualization page ([f3dcf14](https://github.com/LouisPauchet/open-csi-publisher/commit/f3dcf148066ec582c4b36917972c9595a49de999))
* **web:** vendor chartjs-plugin-zoom for interactive chart axes ([3b33455](https://github.com/LouisPauchet/open-csi-publisher/commit/3b33455048ac8e3642a9206d9e623230787c7759))


### Bug Fixes

* **api:** log and map every unhandled exception instead of a silent 500 ([371d153](https://github.com/LouisPauchet/open-csi-publisher/commit/371d1535b982ada5dea4be3a8ef4d80950a8f028))
* **core:** bound dataset build provider calls with a timeout ([500bd52](https://github.com/LouisPauchet/open-csi-publisher/commit/500bd52ebdf753691c04819c884ddec984fe14d2))
* **core:** cap total bytes read per build, exempt the publish endpoint ([410eaca](https://github.com/LouisPauchet/open-csi-publisher/commit/410eaca53a6db8893401f900ce77a180f71d8c54))
* **opendap:** exclude datasets too large to fully cache, harden get_dataset() ([2152711](https://github.com/LouisPauchet/open-csi-publisher/commit/21527117ce3a34cb477f2cb6fe9420871de59b7f))
* **providers:** degrade gracefully instead of crashing on "no data yet" ([8eeacb2](https://github.com/LouisPauchet/open-csi-publisher/commit/8eeacb2fead6916b190048ea52b86ff2b3be9c67))
* **sources:** one broken source must not break every dataset ([52c01e0](https://github.com/LouisPauchet/open-csi-publisher/commit/52c01e09ebe61aee79c3d3f2ed1b156c04725372))
* **web:** render mobile track as a bounding box instead of a full polyline ([25617ac](https://github.com/LouisPauchet/open-csi-publisher/commit/25617ace19b09dfc2245cb73f6bdf4c2efc6e3e0))
* **web:** scope map.js and dataset_panel.js to avoid a global BASE_PATH clash ([15101a9](https://github.com/LouisPauchet/open-csi-publisher/commit/15101a928426ff6db078a6065e4d6d98da57f243))
* **web:** scope map.js to avoid a global BASE_PATH clash ([d28e505](https://github.com/LouisPauchet/open-csi-publisher/commit/d28e5053aabbe23eb7693afc8de05ddca1bff7f5))


### Performance Improvements

* **api:** stop building the full dataset just to view its detail page ([1c76da8](https://github.com/LouisPauchet/open-csi-publisher/commit/1c76da8af2519b64f770bf5cb541889aeed2e419))
* **loggernet:** build archived-file time bounds without a full parse ([39cb8d2](https://github.com/LouisPauchet/open-csi-publisher/commit/39cb8d2e684cb90b1e2f11547e3ea9ad6b99f6be))

## [0.6.0](https://github.com/LouisPauchet/open-csi-publisher/compare/open-csi-publisher-v0.5.0...open-csi-publisher-v0.6.0) (2026-08-07)


### Features

* **settings:** add root_path setting for reverse-proxy subpath deployments ([92307bb](https://github.com/LouisPauchet/open-csi-publisher/commit/92307bb8226d34d8104b825dec7d0e47327c2ec5))
* support mounting under a subpath + CI coverage reporting ([6ad8801](https://github.com/LouisPauchet/open-csi-publisher/commit/6ad8801ab2557b9ef9106c2a9c05283aa8c4873f))
* **web:** prefix map/dataset-panel JS URLs with window.APP_ROOT_PATH ([0093138](https://github.com/LouisPauchet/open-csi-publisher/commit/00931386073ef50cd0827484a6230a7c781c37c7))
* **web:** prefix templates, redirects, and publish URLs with root_path ([ca1d916](https://github.com/LouisPauchet/open-csi-publisher/commit/ca1d91610584ce2c8c1b370497001f7eb84a6f6a))


### Documentation

* document ROOT_PATH subpath deployment ([56c1726](https://github.com/LouisPauchet/open-csi-publisher/commit/56c17261c06e57acf4eba39814e932dd5c6f6e08))

## [0.5.0](https://github.com/LouisPauchet/open-csi-publisher/compare/open-csi-publisher-v0.4.1...open-csi-publisher-v0.5.0) (2026-08-05)


### Features

* add a config validator page for pasting and checking dataset config JSON ([30c84e1](https://github.com/LouisPauchet/open-csi-publisher/commit/30c84e16475e171d8af557153b0c4a889bb56b20))


### Bug Fixes

* make the config validator page scroll, and add line numbers to errors ([90b870e](https://github.com/LouisPauchet/open-csi-publisher/commit/90b870e7c4125422194ca5e0a0da9ac78c8813bb))
* pin the config validator page's footer below content, not mid-page ([343f427](https://github.com/LouisPauchet/open-csi-publisher/commit/343f427fdee2e7166ff6dbadbb1704422e135640))
* stop the variables/deployments tables and kv panels from overflowing their cards ([f805937](https://github.com/LouisPauchet/open-csi-publisher/commit/f8059374457a2af11f1b370400c67306999b82ea))

## [0.4.1](https://github.com/LouisPauchet/open-csi-publisher/compare/open-csi-publisher-v0.4.0...open-csi-publisher-v0.4.1) (2026-07-28)


### Bug Fixes

* flatten multidimensional variables into wide columns instead of duplicated rows ([ad168d8](https://github.com/LouisPauchet/open-csi-publisher/commit/ad168d8f086569fbb6a76e0976e8f363b31523ea))
* register publish endpoint auth as an OpenAPI security scheme ([f8cc90a](https://github.com/LouisPauchet/open-csi-publisher/commit/f8cc90a6be3ec0496a1fff3144a09678894bf92c))
* skip datasets with invalid config instead of failing the whole listing ([e4e57cc](https://github.com/LouisPauchet/open-csi-publisher/commit/e4e57ccd71ca703d8ecb90d19822ee391806b4cb))
* skip datasets with invalid config instead of failing the whole listing ([1229d37](https://github.com/LouisPauchet/open-csi-publisher/commit/1229d37e347f43012d08c902c40859293d7a9d62))


### Documentation

* describe wide-format extra_dimension flattening in REST API docs ([2c8afd0](https://github.com/LouisPauchet/open-csi-publisher/commit/2c8afd0d00676d66d745cf7bcc1617d76015e6ba))

## [0.4.0](https://github.com/LouisPauchet/open-csi-publisher/compare/open-csi-publisher-v0.3.1...open-csi-publisher-v0.4.0) (2026-07-28)


### Features

* add Alembic-based database migrations ([231f146](https://github.com/LouisPauchet/open-csi-publisher/commit/231f1465596d869cb1e13f045dc281b98118373a))
* add Redis-backed cache for parsed file content ([9b855fa](https://github.com/LouisPauchet/open-csi-publisher/commit/9b855fa4423282bb2f5ae4601322b265d5f2afcc))
* cache parsed generic-CSV file content, with a per-station opt-out ([7463ca9](https://github.com/LouisPauchet/open-csi-publisher/commit/7463ca92e4549c7db419d0bbb68baf0a8e33df3d))
* cache parsed LoggerNet file content, with a per-station opt-out ([862d4f0](https://github.com/LouisPauchet/open-csi-publisher/commit/862d4f028b5a74c49b2d9d772a4f2caa19e832d7))
* Redis parsed-file cache, DB-backed config revalidation, and Alembic migrations ([4494df0](https://github.com/LouisPauchet/open-csi-publisher/commit/4494df0de1b16cdfdcb7cc1b076e9780b3127086))
* run database migrations automatically at app startup ([a66eb84](https://github.com/LouisPauchet/open-csi-publisher/commit/a66eb8426b0f60bc09ecdf3f1a5874e30a4cbef5))
* skip station config-hash recheck within a revalidation window ([ae39255](https://github.com/LouisPauchet/open-csi-publisher/commit/ae392555874c69c6095a312146456079718a8f8d))
* wire the parsed-file cache into data provider construction ([1570105](https://github.com/LouisPauchet/open-csi-publisher/commit/1570105a0fd8bd41dda7cebaf66608bdad043247))


### Bug Fixes

* add logernet example config ([01ff41b](https://github.com/LouisPauchet/open-csi-publisher/commit/01ff41b35912fe6beecc36d45b7f74e84910a6d1))
* layout bug ([c219a41](https://github.com/LouisPauchet/open-csi-publisher/commit/c219a41614a88dc462a148a8a80ccf9f51c920cb))
* update footer message ([32208aa](https://github.com/LouisPauchet/open-csi-publisher/commit/32208aaecf529580bf237253b8a4e9f01d046a9f))

## [0.3.1](https://github.com/LouisPauchet/open-csi-publisher/compare/open-csi-publisher-v0.3.0...open-csi-publisher-v0.3.1) (2026-07-22)


### Bug Fixes

* widen file_index.size to BigInteger ([eaba971](https://github.com/LouisPauchet/open-csi-publisher/commit/eaba971de7a58fac9a003ac72dbb305d70af6e89))

## [0.3.0](https://github.com/LouisPauchet/open-csi-publisher/compare/open-csi-publisher-v0.2.0...open-csi-publisher-v0.3.0) (2026-07-22)


### Features

* read ThingsBoard API key from credentials env vars ([03e2a71](https://github.com/LouisPauchet/open-csi-publisher/commit/03e2a71c2384dac62d4921ecbcd002536e04d53d))
* support ThingsBoard API key authentication in client ([26cd3eb](https://github.com/LouisPauchet/open-csi-publisher/commit/26cd3ebea036f44dc8b995005ccb843caa0d063f))


### Bug Fixes

* coerce mixed-type numeric telemetry values and flag data loss ([8e9e504](https://github.com/LouisPauchet/open-csi-publisher/commit/8e9e5048ea14381a9e6dad3b78eb46ac23d4c1b1))


### Documentation

* document ThingsBoard API key as an alternative credential ([5f2bed1](https://github.com/LouisPauchet/open-csi-publisher/commit/5f2bed12f6bf7cc830963943750a0a5fc0416ece))

## [0.2.0](https://github.com/LouisPauchet/open-csi-publisher/compare/open-csi-publisher-v0.1.2...open-csi-publisher-v0.2.0) (2026-07-22)


### Features

* add "validate loggernet" CLI command for batch config validation ([5c51471](https://github.com/LouisPauchet/open-csi-publisher/commit/5c51471f5b82cb53402af48bdc594019c18626f5))
* add Entra ID (OIDC) login and session auth ([8f7e05e](https://github.com/LouisPauchet/open-csi-publisher/commit/8f7e05ec8ff9199c9d933c52c150371a7312dde2))
* add OIDC callback route that establishes the session ([8814462](https://github.com/LouisPauchet/open-csi-publisher/commit/8814462066dcf77b98a6c3b0dbc31f81ea1f55ce))
* add OIDC login route redirecting to Entra ID ([2a1243d](https://github.com/LouisPauchet/open-csi-publisher/commit/2a1243deed17630c865304d4d5d35e1195d39e4d))
* add OIDC logout route ([276b62a](https://github.com/LouisPauchet/open-csi-publisher/commit/276b62a06b776916e9023d23cddae9843062fc82))
* add operational logging to config loading and dataset building ([b56082a](https://github.com/LouisPauchet/open-csi-publisher/commit/b56082aee29f79200f34a0354a85658c51b7d3a5))
* add project creator credit to site footer ([43a1323](https://github.com/LouisPauchet/open-csi-publisher/commit/43a1323c108799da93d0d5f9947a8baaa5efff0c))
* add Settings.oidc_configured completeness check ([7e0c001](https://github.com/LouisPauchet/open-csi-publisher/commit/7e0c0015bc8204fa74acaeb5e659f9a46f906863))
* allow extra_dimension to declare more than one dimension ([72484fb](https://github.com/LouisPauchet/open-csi-publisher/commit/72484fbfd851623d7ab6f9f00ec09bb4031f5959))
* allow loggernet file_pattern without a .dat extension ([4d63bde](https://github.com/LouisPauchet/open-csi-publisher/commit/4d63bdeb814a9660f5a45d5f4e9ce870eb314426))
* harden LoggerNet config/parsing, add validation CLI, switch to loguru ([342ce6a](https://github.com/LouisPauchet/open-csi-publisher/commit/342ce6ad985aaf1e58f8f183e9c59e41f8f12078))
* register session middleware when OIDC is fully configured ([b223acd](https://github.com/LouisPauchet/open-csi-publisher/commit/b223acdb22af3379f3ebcf944afa0f846848ba9d))
* resolve current user from session when OIDC is configured ([214cf33](https://github.com/LouisPauchet/open-csi-publisher/commit/214cf33677fdc40ac3c9be98f5f1fe51120d0a32))
* show login/logout affordance in the site header ([03e9c30](https://github.com/LouisPauchet/open-csi-publisher/commit/03e9c30e4268ab52f49ac34e6ee785a68b9aa209))
* switch project logging to loguru ([08d076d](https://github.com/LouisPauchet/open-csi-publisher/commit/08d076d96f5618d4343efbc3d8b419d14c9ba3d1))
* validate TOA5 header marker and field count explicitly ([c1a4124](https://github.com/LouisPauchet/open-csi-publisher/commit/c1a4124eb98aff1a4226cbf4ec8995c0b0c6d943))


### Bug Fixes

* derive loggernet historical file pattern from actual extension ([c0aba91](https://github.com/LouisPauchet/open-csi-publisher/commit/c0aba91e61d64d1b5c9efb726da9f008df436d17))
* skip files that don't match the TOA5 header shape during matching ([9a4105e](https://github.com/LouisPauchet/open-csi-publisher/commit/9a4105ef1528cf29ecd80c8ae2f33faef67fca43))


### Documentation

* update .env.example now that the OIDC login flow is implemented ([50cf765](https://github.com/LouisPauchet/open-csi-publisher/commit/50cf765c69e51a6f49598d9cfe0861576016945e))

## [0.1.2](https://github.com/LouisPauchet/open-csi-publisher/compare/open-csi-publisher-v0.1.1...open-csi-publisher-v0.1.2) (2026-07-21)


### Bug Fixes

* please release please ([e054433](https://github.com/LouisPauchet/open-csi-publisher/commit/e054433ae8d68a6035fa36ebd91b64d764244937))

## [0.1.1](https://github.com/LouisPauchet/open-csi-publisher/compare/open-csi-publisher-v0.1.0...open-csi-publisher-v0.1.1) (2026-07-20)


### Bug Fixes

* update readme ([81020a2](https://github.com/LouisPauchet/open-csi-publisher/commit/81020a2d164529f1a1f4e6c42bea2f0440656fb5))
