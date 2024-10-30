<?php
/**
 * In order to create the databases, its tables and put some content in it, the
 * operator need to call this script. This script is basically a minimalistic
 * "wp cli" that instanciate the WordPress framework and call the same functions
 * that the installer does, but does not require to have a valid WordPress
 * installation (a `wp-config.php` and `wp-includes/version.php` as the "wp cli"
 * does).
 *
 * As it's calling WordPress code, the `ABSPATH` constant has to be correctly
 * defined. It's meant to stand in the root of the wp-dev directory, but feel
 * free to have it pointing to any directory containing an extract of an
 * WordPress source. See the __WORDPRESS_SOURCE_DIR constant to change it.
 *
 * It also have to be able to connect to the database, so name equivalent to
 * `DB.wordpress-test.svc` have to be accessible. It means that if you want it
 * to work from outside the cluster, you have to use something like KubeVPN.
**/

error_log("  ...  Hello from wp-ops/ensure-wordpress-and-theme.php  ... ");

error_reporting(E_ALL);
ini_set('display_errors', 'On');

$shortops = "h";
$longopts  = array(
    "name:",
    "wp-dir:",
    "wp-host:",
    "db-host:",
    "db-name:",
    "db-user:",
    "db-password:",
	"plugins:",
);
$options = getopt($shortops, $longopts);
if ( key_exists("h", $options) ) {
  $help = <<<EOD

Usage:
  ensure-wordpress-and-theme.php --name="site-a" --path="/site-A"

Options:
  --name        Mandatory  Identifier (as in k8s CR's name). Example: "site-a"
  --wp-host     Mandatory  Hostname (“site_name”) for WordPress
  --db-host     Mandatory  Hostname of the database to connect to
  --db-user     Mandatory  Username of the database to connect to
  --db-password Mandatory  Password for the database to connect to
  --wp-dir      Mandatory  The path to the WordPress installation to load.
  --plugins     Mandatory  List of non-default plugins.
EOD;
  echo $help . "\n";
  exit();
}

function bad_option ($message) {
  echo $message;
  echo "\nUse -h to get additional help.\n";
  exit(1);
}

foreach(["name", "wp-dir", "wp-host",
         "db-host", "db-name", "db-user", "db-password"] as $opt) {
  if ( empty($options[$opt]) ) {
    bad_option("\"--$opt\" is required.");
  }
}

if ( empty($options["title"]) ) {
  $options["title"] = $options["name"];
}


define( 'ABSPATH', $options["wp-dir"]);
define( 'WP_CONTENT_DIR', ABSPATH);  # Meh.
define( 'WP_DEBUG', 1);
define( 'WP_DEBUG_DISPLAY', 1);

define( '__WORDPRESS_DOMAIN', $options["wp-host"] );
define( '__WORDPRESS_DEFAULT_THEME', 'wp-theme-2018' );

$_SERVER['HTTP_HOST'] = __WORDPRESS_DOMAIN;

define("DB_HOST", $options["db-host"]);
define("DB_NAME", $options["db-name"]);
define("DB_USER", $options["db-user"]);
define("DB_PASSWORD", $options["db-password"]);
define("PLUGINS", $options["plugins"]);

global $table_prefix; $table_prefix = "wp_";

define("WP_ADMIN", true);
define("WP_INSTALLING", true);
require_once( ABSPATH . 'wp-settings.php' );

function ensure_plugins ( $options ) {
	$plugins_vars = [
		"epfl-cache-control/epfl-cache-control.php" => [
			"cache_control_front_page_max_age" => 300,
			"cache_control_pages_max_age" => 300,
			"cache_control_categories_max_age" => 300,
			"cache_control_singles_max_age" => 300,
			"cache_control_home_max_age" => 300,
			"cache_control_tags_max_age" => 300,
			"cache_control_authors_max_age" => 300,
			"cache_control_dates_max_age" => 300,
			"cache_control_feeds_max_age" => 300,
			"cache_control_attachment_max_age" => 300,
			"cache_control_search_max_age" => 300,
			"cache_control_notfound_max_age" => 300,
			"cache_control_redirect_permanent_max_age" => 300
		],
		"epfl-coming-soon/epfl-coming-soon.php" => [
			"epfl_csp_options" => 'a:5:{s:6:"status";s:2:"on";s:17:"theme_maintenance";s:2:"no";s:11:"status_code";s:2:"no";s:10:"page_title";s:11:"Coming soon";s:12:"page_content";s:438:"&nbsp;  &nbsp; <p style="text-align: center;"><img class="img-fluid aligncenter" src="https://web2018.epfl.ch/5.0.2/icons/epfl-logo.svg" alt="Logo EPFL" width="388" height="113" /></p>  <h3 style="text-align: center; color: #ff0000; font-family: Helvetica, Arial, sans-serif;">Something new is coming...</h3> <p style="position: absolute; bottom: 0; left: 0; width: 100%; text-align: center;"><a href="wp-admin/">Connexion / Login</a></p>";}',
		],
		"ewww-image-optimizer/ewww-image-optimizer.php" => [
			"exactdn_all_the_things" => '',
			"exactdn_lossy" => '',
			"ewww_image_optimizer_tracking_notice" => '1',
			"ewww_image_optimizer_enable_help_notice" => '1',
			"ewww_image_optimizer_cloud_key" => '',
			"ewww_image_optimizer_jpg_quality" => '',
			"ewww_image_optimizer_include_media_paths" => '1',
			"ewww_image_optimizer_aux_paths" => '',
			"ewww_image_optimizer_exclude_paths" => '',
			"ewww_image_optimizer_allow_tracking" => '',
			"ewww_image_optimizer_maxmediawidth" => '2048',
			"ewww_image_optimizer_maxmediaheight" => '2048',
			"ewww_image_optimizer_resize_existing" => '1',
			"ewww_image_optimizer_disable_resizes" => '',
			"ewww_image_optimizer_disable_resizes_opt" => '',
			"ewww_image_optimizer_jpg_background" => '',
			"ewww_image_optimizer_webp_paths" => '',
			"ewww_image_optimizer_dismiss_media_notice" => '1',
			"ewww_image_optimizer_debug" => ''
		],
		"enlighter/Enlighter.php" => [
			"enlighter-options" => 'a:69:{s:19:"translation-enabled";b:1;s:16:"enlighterjs-init";s:6:"inline";s:21:"enlighterjs-assets-js";b:1;s:25:"enlighterjs-assets-themes";b:1;s:34:"enlighterjs-assets-themes-external";b:0;s:26:"enlighterjs-selector-block";s:18:"pre.EnlighterJSRAW";s:27:"enlighterjs-selector-inline";s:19:"code.EnlighterJSRAW";s:18:"enlighterjs-indent";i:4;s:28:"enlighterjs-ampersandcleanup";b:1;s:21:"enlighterjs-linehover";b:1;s:26:"enlighterjs-rawcodedbclick";b:0;s:24:"enlighterjs-textoverflow";s:5:"break";s:23:"enlighterjs-linenumbers";b:1;s:17:"enlighterjs-theme";s:9:"enlighter";s:21:"enlighterjs-retaincss";b:0;s:18:"toolbar-visibility";s:4:"show";s:18:"toolbar-button-raw";b:1;s:19:"toolbar-button-copy";b:1;s:21:"toolbar-button-window";b:1;s:15:"tinymce-backend";b:0;s:16:"tinymce-frontend";b:0;s:15:"tinymce-formats";b:1;s:17:"tinymce-autowidth";b:0;s:22:"tinymce-tabindentation";b:0;s:25:"tinymce-keyboardshortcuts";b:0;s:12:"tinymce-font";s:13:"sourcecodepro";s:16:"tinymce-fontsize";s:5:"0.7em";s:18:"tinymce-lineheight";s:5:"1.4em";s:13:"tinymce-color";s:7:"#000000";s:15:"tinymce-bgcolor";s:7:"#f9f9f9";s:17:"gutenberg-backend";b:1;s:16:"quicktag-backend";b:0;s:17:"quicktag-frontend";b:0;s:13:"quicktag-mode";s:4:"html";s:14:"shortcode-mode";s:8:"disabled";s:16:"shortcode-inline";b:1;s:22:"shortcode-type-generic";b:0;s:23:"shortcode-type-language";b:0;s:20:"shortcode-type-group";b:0;s:24:"shortcode-filter-content";b:1;s:24:"shortcode-filter-excerpt";b:1;s:23:"shortcode-filter-widget";b:0;s:24:"shortcode-filter-comment";b:0;s:31:"shortcode-filter-commentexcerpt";b:0;s:11:"gfm-enabled";b:0;s:10:"gfm-inline";b:1;s:12:"gfm-language";s:3:"raw";s:18:"gfm-filter-content";b:1;s:18:"gfm-filter-excerpt";b:1;s:17:"gfm-filter-widget";b:0;s:18:"gfm-filter-comment";b:0;s:25:"gfm-filter-commentexcerpt";b:0;s:14:"compat-enabled";b:0;s:13:"compat-crayon";b:0;s:12:"compat-type1";b:0;s:12:"compat-type2";b:0;s:21:"compat-filter-content";b:1;s:21:"compat-filter-excerpt";b:1;s:20:"compat-filter-widget";b:0;s:21:"compat-filter-comment";b:0;s:28:"compat-filter-commentexcerpt";b:0;s:12:"cache-custom";b:0;s:10:"cache-path";s:0:"";s:9:"cache-url";s:0:"";s:27:"dynamic-resource-invocation";b:1;s:19:"ext-infinite-scroll";b:0;s:16:"ext-ajaxcomplete";b:0;s:17:"bbpress-shortcode";b:0;s:16:"bbpress-markdown";b:0;}'
		],
		"wp-media-folder/wp-media-folder.php" => [
			"wpmf_use_taxonomy" => '1',
			"wpmf_gallery_image_size_value" => '["thumbnail","medium","large","full"]',
			"wpmf_padding_masonry" => '5',
			"wpmf_padding_portfolio" => '10',
			"wpmf_usegellery" => '0',
			"wpmf_useorder" => '1',
			"wpmf_create_folder" => 'role',
			"wpmf_option_override" => '1',
			"wpmf_option_duplicate" => '0',
			"wpmf_active_media" => '0',
			"wpmf_folder_option2" => '1',
			"wpmf_option_searchall" => '1',
			"wpmf_usegellery_lightbox" => '0',
			"wpmf_media_rename" => '0',
			"wpmf_patern_rename" => '{sitename} - {foldername} - #',
			"wpmf_rename_number" => '0',
			"wpmf_option_media_remove" => '0',
			"wpmf_default_dimension" => '["400x300","640x480","800x600","1024x768","1600x1200"]',
			"wpmf_selected_dimension" => '["400x300","640x480","800x600","1024x768","1600x1200"]',
			"wpmf_weight_default" => '[["0-61440","kB"],["61440-122880","kB"],["122880-184320","kB"],["184320-245760","kB"],["245760-307200","kB"]]',
			"wpmf_weight_selected" => '[["0-61440","kB"],["61440-122880","kB"],["122880-184320","kB"],["184320-245760","kB"],["245760-307200","kB"]]',
			"wpmf_color_singlefile" => '{"bgdownloadlink":"#444444","hvdownloadlink":"#888888","fontdownloadlink":"#ffffff","hoverfontcolor":"#ffffff"}',
			"wpmf_option_singlefile" => '0',
			"wpmf_option_sync_media" => '0',
			"wpmf_option_sync_media_external" => '0',
			"wpmf_list_sync_media" => "array (
			  )",
			"wpmf_time_sync" => '60',
			"wpmf_lastRun_sync" => '1540467937',
			"wpmf_slider_animation" => 'slide',
			"wpmf_option_mediafolder" => '0',
			"wpmf_option_countfiles" => '1',
			"wpmf_option_lightboximage" => '0',
			"wpmf_option_hoverimg" => '1',
			"wpmf_options_format_title" => 'a:15:{s:6:"hyphen";s:1:"1";s:6:"period";s:1:"0";s:4:"plus";s:1:"0";s:9:"ampersand";s:1:"0";s:15:"square_brackets";s:1:"0";s:14:"curly_brackets";s:1:"0";s:10:"underscore";s:1:"1";s:5:"tilde";s:1:"0";s:4:"hash";s:1:"0";s:6:"number";s:1:"0";s:14:"round_brackets";s:1:"0";s:3:"alt";s:1:"0";s:11:"description";s:1:"0";s:7:"caption";s:1:"0";s:6:"capita";s:7:"cap_all";}',
			"wpmf_image_watermark_apply" => 'a:5:{s:8:"all_size";s:1:"1";s:9:"thumbnail";s:1:"0";s:6:"medium";s:1:"0";s:5:"large";s:1:"0";s:4:"full";s:1:"0";}',
			"wpmf_option_image_watermark" => '0',
			"wpmf_watermark_position" => 'top_left',
			"wpmf_watermark_image" => '',
			"wpmf_watermark_image_id" => '0',
			"wpmf_gallery_settings" => "array (
				'hyphen' => '1',
				'period' => '0',
				'plus' => '0',
				'ampersand' => '0',
				'square_brackets' => '0',
				'curly_brackets' => '0',
				'underscore' => '1',
				'tilde' => '0',
				'hash' => '0',
				'number' => '0',
				'round_brackets' => '0',
				'alt' => '0',
				'description' => '0',
				'caption' => '0',
				'capita' => 'cap_all',
			)",
			"wpmf_settings" => "array (
				'hide_remote_video' => '0',
				'gallery_settings' =>
					array (
						'theme' =>
							array (
								'default_theme' =>
									array (
										'columns' => '3',
										'size' => 'medium',
										'targetsize' => 'large',
										'link' => 'file',
										'orderby' => 'post__in',
										'order' => 'ASC',
									),
								'portfolio_theme' =>
									array (
										'columns' => '3',
										'size' => 'medium',
										'targetsize' => 'large',
										'link' => 'file',
										'orderby' => 'post__in',
										'order' => 'ASC',
									),
								'masonry_theme' =>
									array (
										'columns' => '3',
										'size' => 'medium',
										'targetsize' => 'large',
										'link' => 'file',
										'orderby' => 'post__in',
										'order' => 'ASC',
									),
								'slider_theme' =>
									array (
										'columns' => '3',
										'size' => 'medium',
										'targetsize' => 'large',
										'link' => 'file',
										'orderby' => 'post__in',
										'animation' => 'slide',
										'duration' => '4000',
										'order' => 'ASC',
										'auto_animation' => '1',
									),
							),
					),
				'watermark_exclude_folders' =>
					array (
						0 => '0',
					),
				'folder_design' => 'material_design',
				'load_gif' => '1',
				'hide_tree' => '1',
				'watermark_margin' =>
					array (
						'top' => '0',
						'right' => '0',
						'bottom' => '0',
						'left' => '0',
					),
				'watermark_image_scaling' => '100',
				'format_mediatitle' => '1',
			)",
			"_wpmf_import_order_notice_flag" => 'yes',
			"can_compress_scripts" => '0'
		]
	];
  # This is the default plugin list that should be activated at installation
  $defaultPlugins = array(
    "Polylang",
    "EPFL-Content-Filter/EPFL-Content-Filter.php",
    "EPFL-settings/EPFL-settings.php",
    "accred/EPFL-Accred.php",
    "enlighter/Enlighter.php",
    "epfl-404/epfl-404.php",
    "epfl-cache-control/epfl-cache-control.php",
    "epfl-coming-soon/epfl-coming-soon.php",
    "epfl-intranet/epfl-intranet.php",
    // "epfl-menus/epfl-menus.php",
    "epfl-remote-content-shortcode/epfl-remote-content-shortcode.php",
    "ewww-image-optimizer/ewww-image-optimizer.php",
    "find-my-blocks/find-my-blocks.php",
    "flowpaper-lite-pdf-flipbook/flowpaper.php",
    "svg-support/svg-support.php",
    "tequila/EPFL-Tequila.php",
    "tinymce-advanced/tinymce-advanced.php",
    "very-simple-meta-description/vsmd.php",
    "wp-gutenberg-epfl/plugin.php",
    "wp-media-folder/wp-media-folder.php"
  );

  $specificPlugin = explode(',', PLUGINS);
  $pluginlist = array_merge($defaultPlugins, $specificPlugin);

  $pluginPathArray = [];
	foreach ($pluginlist as $pluginName) {
		$plugin = Plugin::create($pluginName);
		$pluginPathArray[] = $plugin.getPluginPath();
		$plugin.updateOptions();
	}
	update_option( 'active_plugins', $pluginPathArray );

}

ensure_plugins( $options );

echo "WordPress plugins successfully installed";
