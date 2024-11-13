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

	public function updateOptions()
	{
		update_option( 'polylang_wpml_strings', $this->polylang_wpml_strings );
		update_option( 'widget_polylang', $this->widget_polylang );
		update_option( 'polylang', $this->polylangOptions );

		if (!is_plugin_active($this->pluginPath)) {
			activate_plugin($this->pluginPath);
			echo " \nPolylang plugin activated \n";
		}

		require_once $this->wpDirPath . 'wp-content/plugins/polylang/polylang.php';
		$polylangInstance = new PLL_Admin_Model($this->polylangOptions);
		$languageMap = [
			'en' => ['name' => 'English', 'locale' => 'en_US'],
			'es' => ['name' => 'Spanish', 'locale' => 'es_ES'],
			'fr' => ['name' => 'French', 'locale' => 'fr_FR'],
			'de' => ['name' => 'German', 'locale' => 'de_DE'],
			'it' => ['name' => 'Italian', 'locale' => 'it_IT'],
		];

		foreach ($this->languagesList as $slug) {
			if (array_key_exists($slug, $languageMap)) {
				$args = array(
					'slug' => $slug,
					'name' => $languageMap[$slug]['name'],
					'locale' => $languageMap[$slug]['locale']
				);
				$polylangInstance->add_language($args);
			}
		}
	}
}
