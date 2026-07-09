import React from 'react';
import { View, Text, ScrollView } from 'react-native';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
  }

  render() {
    if (this.state.hasError) {
      return (
        <View style={{ flex: 1, paddingTop: 50, backgroundColor: 'red', paddingHorizontal: 20 }}>
          <ScrollView>
            <Text style={{ color: 'white', fontSize: 24, fontWeight: 'bold' }}>CRASH DETECTED!</Text>
            <Text style={{ color: 'yellow', marginTop: 15, fontSize: 16 }}>
              {this.state.error && this.state.error.toString()}
            </Text>
            <Text style={{ color: 'white', marginTop: 15, fontSize: 12 }}>
              {this.state.errorInfo && this.state.errorInfo.componentStack}
            </Text>
          </ScrollView>
        </View>
      );
    }
    return this.props.children;
  }
}
