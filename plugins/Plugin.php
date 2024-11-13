<?php

$files = glob('./plugins/*.php');

foreach ($files as $file) {
	if ($file != 'Plugin.php'){
		require_once($file);
	}
}

abstract class Plugin {
	protected $pluginPath;
	protected $secrets_dir;

	public static function create($pluginName, $unit_id, $secrets_dir, $languagesList, $wpDirPath) {
		$pluginDict = array(
			'Polylang' => new PolylangPlugin($languagesList, $wpDirPath),
			'EPFL-Content-Filter' => new EPFLContentFilter(),
			'EPFL-settings'  => new EPFLSettings(),
			'EPFL-Accred'  => new EPFLAccred($unit_id),
			'Enlighter'  => new Enlighter(),
			'EPFL-404'  => new EPFL404(),
			'epfl-cache-control'  => new EPFLCacheControl(),
			'epfl-coming-soon'  => new EPFLComingSoon(),
			'epfl-menus'  => new EPFLMenus(),
			'epfl-remote-content-shortcode'  => new EPFLRemoteContentShortcode(),
			'ewww-image-optimizer'  => new EwwwImageOptimizer(),
			'find-my-blocks'  => new FindMyBlocks(),
			'flowpaper'  => new Flowpaper(),
			'svg-support'  => new SVGSupport(),
			'EPFL-Tequila'  => new EPFLTequila(),
			'tinymce-advanced'  => new TinymceAdvanced(),
			'vsmd'  => new VSMD(),
			'wp-gutenberg-epfl'  => new WPGutenbergEpfl(),
			'wp-media-folder' => new WPMediaFolder(),
			'Inside' => new EPFLIntranet(),
			'EPFLRestauration' => new EPFLRestauration(),
			'Emploi' => new Emploi(),
			'Library' => new Library(),
			'CDHSHS' => new CDHSHS(),
			'WPForms' => new WPForms(),
			'Payonline' => new Payonline(),
			'Surveys' => new Surveys(),
			'DiplomaVerification' => new DiplomaVerification(),
			'PartnerUniversities' => new PartnerUniversities()
		);
		if (array_key_exists($pluginName, $pluginDict)) {
			$plugin = $pluginDict[$pluginName];
			$plugin->secrets_dir = $secrets_dir;
			return $plugin;
		} else {
			throw new Exception("Plugin not found: $pluginName");
		}
	}

	public function updateOptions()
	{
		foreach (get_object_vars($this) as $property => $value) {
			if ($property != 'pluginPath') {
				update_option( $property, $value );
			}
		}
	}

	public function getPluginPath(): string
	{
		return $this->pluginPath;
	}

	public function getSecretValue($secretName): string {
		$myfile = fopen("$this->secrets_dir/$secretName", "r") or die("Unable to open file!");
		$secret_value = fread($myfile,filesize("$this->secrets_dir/$secretName"));
		fclose($myfile);
		return $secret_value;
	}
}
