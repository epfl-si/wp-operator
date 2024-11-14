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
			'EPFL-Content-Filter' => new EPFLContentFilterPlugin(),
			'EPFL-settings'  => new EPFLSettingsPlugin(),
			'EPFL-Accred'  => new EPFLAccredPlugin($unit_id),
			'Enlighter'  => new EnlighterPlugin(),
			'EPFL-404'  => new EPFL404Plugin(),
			'epfl-cache-control'  => new EPFLCacheControlPlugin(),
			'epfl-coming-soon'  => new EPFLComingSoonPlugin(),
			'epfl-menus'  => new EPFLMenusPlugin(),
			'epfl-remote-content-shortcode'  => new EPFLRemoteContentShortcodePlugin(),
			'ewww-image-optimizer'  => new EwwwImageOptimizerPlugin(),
			'find-my-blocks'  => new FindMyBlocksPlugin(),
			'flowpaper'  => new FlowpaperPlugin(),
			'svg-support'  => new SVGSupportPlugin(),
			'EPFL-Tequila'  => new EPFLTequilaPlugin(),
			'tinymce-advanced'  => new TinymceAdvancedPlugin(),
			'vsmd'  => new VSMDPlugin(),
			'wp-gutenberg-epfl'  => new WPGutenbergEpflPlugin(),
			'wp-media-folder' => new WPMediaFolderPlugin(),
			'Inside' => new EPFLIntranetPlugin(),
			'EPFLRestauration' => new EPFLRestaurationPlugin(),
			'Emploi' => new EmploiPlugin(),
			'Library' => new LibraryPlugin(),
			'CDHSHS' => new CDHSHSPlugin(),
			'WPForms' => new WPFormsPlugin(),
			'Payonline' => new PayonlinePlugin(),
			'Surveys' => new SurveysPlugin(),
			'DiplomaVerification' => new DiplomaVerificationPlugin(),
			'PartnerUniversities' => new PartnerUniversitiesPlugin()
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
