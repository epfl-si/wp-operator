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

require_once("./plugins/Plugin.php");

error_log("  ...  Hello from wp-ops/ensure-wordpress-and-theme.php  ... ");

error_reporting(E_ALL);
ini_set('display_errors', 'On');

$shortops = "h";
$longopts  = array(
    "name:",
    "wp-dir:",
    "path:",
    "title::",
    "tagline::",
    "theme::",
    "discourage::",
    "wp-host:",
    "db-host:",
    "db-name:",
    "db-user:",
    "db-password:",
    "plugins:",
    "unit-id:",
    "languages:",
    "secret-dir:"
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
  --path        Mandatory  URL's path of the site. Example: "/site-A"
  --title       Optional   Site's title (blogname). Example: "This is the site A"
                           Default set to --name.
  --tagline     Optional   Site's description (tagline). Example: "A site about A and a."
  --theme       Optional   Set the site's theme.
                           Default to __WORDPRESS_DEFAULT_THEME (wp-theme-2018)
  --discourage  Optional   Set search engine visibility. 1 means discourage search
                           engines from indexing this site, but it is up to search
                           engines to honor this request.
  --plugins     Mandatory  List of non-default plugins.
  --unit-id     Mandatory  Plugin unit ID
  --languages	Mandatory  List of languages
  --secret-dir  Mandatory  Secret file's folder
EOD;
  echo $help . "\n";
  exit();
}

function bad_option ($message) {
  echo $message;
  echo "\nUse -h to get additional help.\n";
  exit(1);
}

foreach(["name", "path", "wp-dir", "wp-host",
         "db-host", "db-name", "db-user", "db-password"] as $opt) {
  if ( empty($options[$opt]) ) {
    bad_option("\"--$opt\" is required.");
  }
}

if ( empty($options["title"]) ) {
  $options["title"] = $options["name"];
}

define( 'ABSPATH', $options["wp-dir"]);
define( 'WP_CONTENT_DIR', ABSPATH . 'wp-content' );
define( 'WP_PLUGIN_DIR', WP_CONTENT_DIR . '/plugins' );
define( 'WP_DEBUG', 1);
define( 'WP_DEBUG_DISPLAY', 1);

define( '__WORDPRESS_DOMAIN', $options["wp-host"] );
define( '__WORDPRESS_DEFAULT_THEME', 'wp-theme-2018' );


function ensure_clean_site_url($path) {
  $site_url = __WORDPRESS_DOMAIN . "/{$path}/";
  return preg_replace('#/+#','/', $site_url);
}
define("WP_SITEURL", "https://" . ensure_clean_site_url($options["path"]));

$_SERVER['HTTP_HOST'] = __WORDPRESS_DOMAIN;

define("DB_HOST", $options["db-host"]);
define("DB_NAME", $options["db-name"]);
define("DB_USER", $options["db-user"]);
define("DB_PASSWORD", $options["db-password"]);
define("PLUGINS", $options["plugins"] ?? null);
define("UNIT_ID", $options["unit-id"]);
define("LANGUAGES", $options["languages"]);
define("SECRETS_DIR", $options["secret-dir"]);

global $table_prefix; $table_prefix = "wp_";

define("WP_ADMIN", true);
define("WP_INSTALLING", true);
require_once( ABSPATH . 'wp-settings.php' );
require_once( ABSPATH . 'wp-admin/includes/plugin.php' );

function ensure_db_schema () {
  require_once( ABSPATH . 'wp-admin/includes/upgrade.php' );
  if (! is_blog_installed()) {
    make_db_current_silent();
  }
  populate_options();
  populate_roles();
  wp_upgrade();
}

function ensure_admin_user ($user_name, $user_email, $user_password) {
  if (! username_exists($user_name)) {
    wp_create_user( $user_name, $user_password, $user_email );
  }
  $user = new WP_User( username_exists($user_name) );
  $user->set_role( 'administrator' );
  update_option( 'admin_email', $user_email );
}

function get_admin_user_id () {
  return 1;  // wp-cli does same
}

/**
 * Whatever wp_install does, that was not already done above.
 */
function ensure_other_basic_wordpress_things ( $options ) {
  # Set search engine visibility. 1 means discourage search engines from
  # indexing this site, but it is up to search engines to honor this request.
  update_option( 'blog_public', ( empty($options["discourage"]) ? '1' : '0' ) );
  update_option( 'fresh_site', 1 );
  update_option( 'siteurl', wp_guess_url() );
  update_option( 'permalink_structure', '/%postname%/' );

  # Use a page as home page, instead of posts.
  update_option( 'show_on_front', 'page' );
  update_option( 'page_on_front', 2 ); // This is the sample page

  wp_install_defaults( get_admin_user_id() );
  wp_install_maybe_enable_pretty_permalinks();

  flush_rewrite_rules();

  wp_cache_flush();
}

function ensure_site_title ( $options ) {
  update_option( 'blogname', stripslashes($options["title"]) );
}

function ensure_tagline ( $options ) {
  if ( !empty($options["tagline"]) ) {
    update_option( 'blogdescription', stripslashes($options["tagline"]) );
  }
}

function ensure_theme ( $options ) {
  if ( empty( $options[ 'theme' ] ) ) {
    $options[ 'theme' ] = __WORDPRESS_DEFAULT_THEME;
  }
  global $wp_theme_directories; $wp_theme_directories = [];
  require_once( ABSPATH . 'wp-includes/theme.php' );

  $theme = wp_get_theme( $options[ 'theme' ] );
  print( switch_theme( $theme->get_stylesheet() ) );
}

function ensure_plugins () {
  # This is the default plugin list that should be activated at installation
  $defaultPlugins = array(
    "Polylang",
    "EPFL-Content-Filter",
    "EPFL-settings",
    "EPFL-Accred",
    "Enlighter",
    "EPFL-404",
    "epfl-cache-control",
    "epfl-coming-soon",
    "epfl-remote-content-shortcode",
    "ewww-image-optimizer",
    "find-my-blocks",
    "flowpaper",
    "EPFL-Tequila",
    "tinymce-advanced",
    "vsmd",
    "wp-gutenberg-epfl",
    "wp-media-folder"
  );

  $specificPlugin = [];
  if (PLUGINS !== null) {
    $specificPlugin = explode(',', PLUGINS);
  }
  $pluginList = array_merge($defaultPlugins, $specificPlugin);

  $languagesList = explode(',', LANGUAGES);

  foreach ($pluginList as $pluginName) {
    $plugin = Plugin::create($pluginName, UNIT_ID, SECRETS_DIR, $languagesList, ABSPATH);
    $activatedPlugin = activate_plugin($plugin->getPluginPath());
    if ($activatedPlugin instanceof WP_Error) {
      throw new ErrorException(var_dump($activatedPlugin->errors) . " - " . $plugin->getPluginPath());
    }
    $plugin->addSpecialConfiguration();
    $plugin->updateOptions();
  }
}

function delete_default_pages_and_posts () {
  $pages = get_posts([
    'post_type' => ['page', 'post'],
    'posts_per_page' => -1, // get all
    'post_status' => array_keys(get_post_statuses()), // all post statuses (publish, draft, private etc...)
  ]);

  foreach ($pages as $page) {
    wp_delete_post($page->ID, true);
  }
}

// https://stackoverflow.com/a/31284266
function generate_random_password(
  $keyspace = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
) {
  $str = '';
  $max = mb_strlen($keyspace, '8bit') - 1;
  if ($max < 1) {
    throw new Exception('$keyspace must be at least two characters long');
  }
  for ($i = 0; $i < 32; ++$i) {
    $str .= $keyspace[random_int(0, $max)];
  }
  return $str;
}

ensure_db_schema();
ensure_other_basic_wordpress_things( $options );
ensure_admin_user( "admin", "admin@exemple.com", generate_random_password() );
ensure_site_title( $options );
ensure_tagline( $options );
ensure_theme( $options );
delete_default_pages_and_posts();
ensure_plugins();

echo "WordPress and plugins successfully installed";
