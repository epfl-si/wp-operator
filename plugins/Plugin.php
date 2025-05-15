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
      'accred' => new EPFLAccredPlugin($unit_id),
      'enlighter' => new EnlighterPlugin(),
      'epfl-404' => new EPFL404Plugin(),
      'epfl-cache-control' => new EPFLCacheControlPlugin(),
      'epfl-coming-soon' => new EPFLComingSoonPlugin(),
      'EPFL-Content-Filter' => new EPFLContentFilterPlugin(),
      'epfl-courses-se' => new CDHSHSPlugin(),
      'epfl-diploma-verification' => new DiplomaVerificationPlugin(),
      'epfl-intranet' => new EPFLIntranetPlugin(),
      'EPFL-Library-Plugins' => new LibraryPlugin(),
      'epfl-menus' => new EPFLMenusPlugin(),
      'epfl-partner-universities' => new PartnerUniversitiesPlugin(),
      'epfl-remote-content-shortcode' => new EPFLRemoteContentShortcodePlugin(),
      'epfl-restauration' => new EPFLRestaurationPlugin(),
      'EPFL-settings' => new EPFLSettingsPlugin(),
      'ewww-image-optimizer' => new EwwwImageOptimizerPlugin(),
      'find-my-blocks' => new FindMyBlocksPlugin(),
      'flowpaper-lite-pdf-flipbook' => new FlowpaperPlugin(),
      'polylang' => new PolylangPlugin($languagesList, $wpDirPath),
      'redirection' => new RedirectionPlugin(),
      'tequila' => new EPFLTequilaPlugin(),
      'tinymce-advanced' => new TinymceAdvancedPlugin(),
      'very-simple-meta-description' => new VSMDPlugin(),
      'wp-gutenberg-epfl' => new WPGutenbergEpflPlugin(),
      'wp-media-folder' => new WPMediaFolderPlugin(),
      'wp-plugin-pushgateway' => new WP_PushgatewayPlugin(),
      'wpforms' => new WPFormsPlugin(),
      'wpforms-epfl-payonline' => new PayonlinePlugin(),
      'wpforms-surveys-polls' => new SurveysPlugin(),
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
