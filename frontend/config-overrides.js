module.exports = function override(config, env) {
  // Remove ForkTsCheckerWebpackPlugin to completely bypass TypeScript checking
  config.plugins = config.plugins.filter(
    plugin => plugin.constructor.name !== 'ForkTsCheckerWebpackPlugin'
  );
  
  // Remove ESLintWebpackPlugin to avoid schema validation issues
  config.plugins = config.plugins.filter(
    plugin => plugin.constructor.name !== 'ESLintWebpackPlugin'
  );
  
  // Optimize chunk splitting for better caching and parallel loading
  if (env === 'production') {
    config.optimization = {
      ...config.optimization,
      splitChunks: {
        chunks: 'all',
        cacheGroups: {
          // Vendor chunks
          react: {
            test: /[\\/]node_modules[\\/](react|react-dom|react-router-dom)[\\/]/,
            name: 'react-vendors',
            priority: 40,
          },
          mui: {
            test: /[\\/]node_modules[\\/](@mui|@emotion)[\\/]/,
            name: 'mui-vendors',
            priority: 35,
          },
          pdf: {
            test: /[\\/]node_modules[\\/](pdfjs-dist|react-pdf|jspdf)[\\/]/,
            name: 'pdf-vendors',
            priority: 30,
          },
          charts: {
            test: /[\\/]node_modules[\\/](recharts|d3-.*)[\\/]/,
            name: 'chart-vendors',
            priority: 25,
          },
          // Common vendors
          vendors: {
            test: /[\\/]node_modules[\\/]/,
            name: 'vendors',
            priority: 10,
          },
          // Common app code
          common: {
            minChunks: 2,
            priority: 5,
            reuseExistingChunk: true,
          },
        },
      },
      // Better runtime chunk for caching
      runtimeChunk: 'single',
    };
  }
  
  return config;
};
