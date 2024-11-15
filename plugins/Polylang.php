<?php

class PolylangPlugin extends Plugin
{
	protected $pluginPath = "polylang/polylang.php";
	private $polylang_wpml_strings = array (
	);
	private $widget_polylang = array (
		'_multiwidget' => 1,
	);
	private $languagesList;
	private $wpDirPath;
	private $polylangOptions;

	function __construct($languagesList, $wpDirPath) {
		$this->languagesList = $languagesList;
		$this->wpDirPath = $wpDirPath;
		$defaultLanguage = !empty($this->languagesList) ? $this->languagesList[0] : 'en';
		$this->polylangOptions = array (
			'browser' => 0,
			'rewrite' => 1,
			'hide_default' => 1,
			'force_lang' => 1,
			'redirect_lang' => 0,
			'media_support' => 0,
			'uninstall' => 0,
			'sync' =>
				array (
				),
			'post_types' =>
				array (
				),
			'taxonomies' =>
				array (
				),
			'domains' =>
				array (
				),
			'version' => '3.5.4',
			'first_activation' => time(),
			'default_lang' => $defaultLanguage
		);
	}

	public function addSpecialConfiguration() {
		require_once $this->wpDirPath . 'wp-content/plugins/polylang/polylang.php';
		$polylangInstance = new PLL_Admin_Model($this->polylangOptions);
		$polylangInstance->set_languages_ready();
		$languageMap = [
			'en' => ['name' => 'English', 'locale' => 'en_US', 'rtl' => 0, 'term_group' => 0, 'flag' => 'us'],
			'fr' => ['name' => 'Français', 'locale' => 'fr_FR', 'rtl' => 0, 'term_group' => 1, 'flag' => 'fr'],
			'de' => ['name' => 'Deutsch', 'locale' => 'de_DE', 'rtl' => 0, 'term_group' => 2, 'flag' => 'de'],
			'it' => ['name' => 'Italiano', 'locale' => 'it_IT', 'rtl' => 0, 'term_group' => 3, 'flag' => 'it'],
			'es' => ['name' => 'Español', 'locale' => 'es_ES', 'rtl' => 0, 'term_group' => 4, 'flag' => 'es'],
			'el' => ['name' => 'Ελληνικά', 'locale' => 'el', 'rtl' => 0, 'term_group' => 5, 'flag' => 'gr'],
			'ro' => ['name' => 'Română', 'locale' => 'ro_RO', 'rtl' => 0, 'term_group' => 6, 'flag' => 'ro'],
		];

		foreach ($this->languagesList as $slug) {
			if (array_key_exists($slug, $languageMap)) {
				$args = array(
					'slug' => $slug,
					'name' => $languageMap[$slug]['name'],
					'locale' => $languageMap[$slug]['locale'],
					'rtl' => $languageMap[$slug]['rtl'],
					'term_group' => $languageMap[$slug]['term_group'],
					'flag' => $languageMap[$slug]['flag'],
				);
				$polylangInstance->add_language($args);

				if (function_exists('wp_download_language_pack')) {
					wp_download_language_pack($languageMap[$slug]['locale']);
				}
			}
		}

		update_option('polylang_wizard_done', true);
		update_option('polylang_settings', array_merge(
			(array) get_option('polylang_settings', []),
			['wizard' => false]
		));
		/*$languages = include $this->wpDirPath . 'wp-content/plugins/polylang/settings/languages.php';
		$polylangInstance = new PLL_Admin_Model($this->polylangOptions);

		$slugMap = array(
			'en' => 'us',
			'el' => 'gr'
		);

		foreach ($this->languagesList as $index => $slug) {
			$language = null;
			$searchSlug = $slug;
			if (array_key_exists($slug, $slugMap)) {
				$searchSlug = $slugMap[$slug];
			}

			foreach ($languages as $key => $item) {
				if (isset($item['flag']) && $item['flag'] === $searchSlug) {
					$language = $item;
					break;
				}
			}
			print_r(" \n " . $slug . " - " . $language. " \n ");

			$args = array(
				'slug' => $slug,
				'name' => $language['name'],
				'locale' => $language['locale'],
				'rtl' => 0,
				'term_group' => $index,
				'flag' => $language['flag'],
			);
			$polylangInstance->add_language($args);

			if (function_exists('wp_download_language_pack')) {
				wp_download_language_pack($language['locale']);
			}
		}*/
	}

	public function updateOptions()
	{
		update_option( 'polylang_wpml_strings', $this->polylang_wpml_strings );
		update_option( 'widget_polylang', $this->widget_polylang );
		update_option( 'polylang', $this->polylangOptions );
	}
}
