#
# Copyright (c) 2022 Nordic Semiconductor
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#

zephyr_library_named(wifi_credentials)
zephyr_library_sources(wifi_credentials.c)

if (CONFIG_WIFI_CREDENTIALS_BACKEND_PSA)
zephyr_library_include_directories(
	$<TARGET_PROPERTY:tfm,TFM_BINARY_DIR>/install/interface/include
)
endif()

zephyr_library_sources_ifdef(
	CONFIG_WIFI_CREDENTIALS_BACKEND_SETTINGS
	wifi_credentials_backend_settings.c)

zephyr_library_sources_ifdef(
	CONFIG_WIFI_CREDENTIALS_BACKEND_PSA
	wifi_credentials_backend_psa.c)
