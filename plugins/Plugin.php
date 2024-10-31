<?php

$files = glob('./plugins/*.php');

foreach ($files as $file) {
	if ($file != 'Plugin.php'){
		require_once($file);
	}
}

abstract class Plugin {
	protected $pluginPath;

	public static function create($pluginName) {
		switch ($pluginName) {
			case 'Polylang':
				return new Polylang();
			case 'EPFL-Content-Filter':
				return new EPFLContentFilter();
			case 'EPFL-settings' :
				return new EPFLSettings();
			case 'EPFL-Accred' :
				return new EPFLAccred();
			case 'Enlighter' :
				return new Enlighter();
			case 'EPFL-404' :
				return new EPFL404();
			case 'epfl-cache-control' :
				return new EPFLCacheControl();
			case 'epfl-coming-soon' :
				return new EPFLComingSoon();
			case 'epfl-intranet ':
				return new EPFLIntranet();
			case 'epfl-menus' :
				return new EPFLMenus();
			case 'epfl-remote-content-shortcode' :
				return new EPFLRemoteContentShortcode();
			case 'ewww-image-optimizer' :
				return new EwwwImageOptimizer();
			case 'find-my-blocks' :
				return new FindMyBlocks();
			case 'flowpaper' :
				return new Flowpaper();
			case 'svg-support' :
				return new SVGSupport();
			case 'EPFL-Tequila' :
				return new EPFLTequila();
			case 'tinymce-advanced' :
				return new TinymceAdvanced();
			case 'vsmd' :
				return new VSMD();
			case 'wp-gutenberg-epfl' :
				return new WPGutenbergEpfl();
			case 'wp-media-folder':
				return new WPMediaFolder();
			case 'EPFLRestauration':
				return new EPFLRestauration();
			default:
				throw new Exception( 'Unknown plugin ');
		}
	}

	# TODO aggiungere tutti gli altri plugins
	# TODO finire le opzioni
	# TODO vérificare i nomi con le catgorie

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
}
