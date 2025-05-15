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
      'epfl-courses-se' => new CDHSHSPlugin(),
      'epfl-diploma-verification' => new DiplomaVerificationPlugin(),
      'enlighter' => new EnlighterPlugin(),
      'epfl-404' => new EPFL404Plugin(),
      'accred' => new EPFLAccredPlugin($unit_id),
      'epfl-cache-control' => new EPFLCacheControlPlugin(),
      'epfl-coming-soon' => new EPFLComingSoonPlugin(),
      'EPFL-Content-Filter' => new EPFLContentFilterPlugin(),
      'epfl-menus' => new EPFLMenusPlugin(),
      'epfl-remote-content-shortcode' => new EPFLRemoteContentShortcodePlugin(),
      'EPFL-settings' => new EPFLSettingsPlugin(),
      'tequila' => new EPFLTequilaPlugin(),
      'ewww-image-optimizer' => new EwwwImageOptimizerPlugin(),
      'find-my-blocks' => new FindMyBlocksPlugin(),
      'flowpaper-lite-pdf-flipbook' => new FlowpaperPlugin(),
      'epfl-intranet' => new EPFLIntranetPlugin(),
      'EPFL-Library-Plugins' => new LibraryPlugin(),
      'epfl-partner-universities' => new PartnerUniversitiesPlugin(),
      'polylang' => new PolylangPlugin($languagesList, $wpDirPath),
      'wpforms-epfl-payonline' => new PayonlinePlugin(),
      'redirection' => new RedirectionPlugin(),
      'epfl-restauration' => new EPFLRestaurationPlugin(),
      'wpforms-surveys-polls' => new SurveysPlugin(),
      'tinymce-advanced' => new TinymceAdvancedPlugin(),
      'very-simple-meta-description' => new VSMDPlugin(),
      'wpforms' => new WPFormsPlugin(),
      'wp-gutenberg-epfl' => new WPGutenbergEpflPlugin(),
      'wp-media-folder' => new WPMediaFolderPlugin(),
    );
    if (array_key_exists($pluginName, $pluginDict)) {
      $plugin = $pluginDict[$pluginName];
      $plugin->secrets_dir = $secrets_dir;
      return $plugin;
    } else {
      throw new Exception("Plugin not found: $pluginName");
    }
  }

  public function addSpecialConfiguration() {}

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

  # kubectl get secrets -n wordpress-test wp-plugin-secrets -o json
  # The pod "operator" will need to consume this secret as a mounted directory with this structure
  public function getSecretValue($secretName): string {
    $myfile = fopen("$this->secrets_dir/$secretName", "r") or die("Unable to open file! Please run the `dev/scripts.sh` script.");
    $secret_value = fread($myfile,filesize("$this->secrets_dir/$secretName"));
    fclose($myfile);
    return $secret_value;
  }
}
