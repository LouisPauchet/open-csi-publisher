# Changelog

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
